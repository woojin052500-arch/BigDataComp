"""
OSM 부산 보행 도로망·계단 추출 — 본인 맥 터미널 전용

분석 환경(클라우드·로컬 VM)은 overpass-api.de / geofabrik / openstreetmap.org 가
모두 프록시에서 차단돼 osmnx 호출이 불가능하다. 이 스크립트만 네트워크가 열린
맥 터미널에서 직접 돌리고, 산출물(GraphML·GeoPackage)을 data/raw/ 에 남긴다.
이후 파이프라인은 그 파일만 읽으므로 다시 네트워크가 필요하지 않다.

지역 범위는 Nominatim 지오코딩이 아니라 이미 확보한 행정동 경계
(data/raw/sgis_admdong_busan_20260701.geojson)로 잡는다.
도로망과 행정경계가 같은 경계선을 쓰게 되어 이후 클리핑에서 어긋나지 않는다.

사용법
    python3 src/osm_extract.py                # 부산 전역
    python3 src/osm_extract.py 중구 동구 서구   # 파일럿(구 이름 나열)

전역은 다운로드에 수십 분, 메모리 수 GB가 든다. 먼저 파일럿으로 한 번 돌려
파이프라인이 도는 것을 확인한 뒤 전역을 거는 편이 안전하다.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
BOUNDARY = RAW / "sgis_admdong_busan_20260701.geojson"
TODAY = date.today().strftime("%Y%m%d")

CRS_WORK = "EPSG:5187"   # 동부원점 TM. 부산은 129도 부근이라 5186이 아니다.


def main() -> int:
    try:
        import osmnx as ox
        import geopandas as gpd
        import networkx as nx
        from shapely.ops import unary_union
    except ImportError as e:
        print(f"패키지 없음: {e}")
        print("설치:  pip3 install osmnx geopandas networkx")
        return 1

    print(f"osmnx {ox.__version__} / geopandas {gpd.__version__}")

    # osmnx 1.x 와 2.x 의 설정 이름이 다르다. 둘 다 시도한다.
    for attr, val in (("requests_timeout", 600), ("timeout", 600),
                      ("log_console", True), ("use_cache", True)):
        try:
            setattr(ox.settings, attr, val)
        except Exception:
            pass

    if not BOUNDARY.exists():
        print(f"경계 파일이 없다: {BOUNDARY}")
        return 1

    gdf = gpd.read_file(BOUNDARY)
    # zsh는 대화형 셸에서 '#'을 주석으로 보지 않는다.
    # 안내문의 주석까지 통째로 붙여넣으면 그대로 인자로 들어오므로 여기서 잘라낸다.
    picks = []
    for a in sys.argv[1:]:
        if a.startswith("#"):
            break
        picks.append(a)
    if picks:
        gdf = gdf[gdf["sggnm"].isin(picks)]
        if gdf.empty:
            print(f"해당 구·군이 경계 파일에 없다: {picks}")
            print("가능한 값:", sorted(gpd.read_file(BOUNDARY)["sggnm"].unique()))
            return 1
        tag = "_".join(picks)
    else:
        tag = "busan"
    print(f"대상 {tag} · 행정동 {len(gdf)}개")

    # 폴리곤 정점이 너무 많으면 Overpass 질의가 깨진다. 약간 단순화하고 봉합한다.
    poly = unary_union(gdf.geometry.values)
    poly = poly.buffer(0.0006).simplify(0.0004).buffer(0)
    print(f"질의 폴리곤 정점 {len(poly.exterior.coords) if poly.geom_type=='Polygon' else 'multi'}")

    print("\n[1/4] 보행 도로망 내려받는 중 (오래 걸린다)")
    G = ox.graph_from_polygon(poly, network_type="walk", simplify=True, retain_all=False)
    print(f"    노드 {G.number_of_nodes():,} · 엣지 {G.number_of_edges():,}")

    print("[2/4] 투영과 길이 계산")
    Gp = ox.project_graph(G, to_crs=CRS_WORK)
    nodes, edges = ox.graph_to_gdfs(Gp)
    edges["length_m"] = edges.geometry.length

    print("[3/4] 계단(highway=steps) 내려받는 중")
    try:
        steps = ox.features_from_polygon(poly, tags={"highway": "steps"})
        steps = steps.to_crs(CRS_WORK)
        n_steps = len(steps)
    except Exception as e:
        print(f"    계단 조회 실패: {e}")
        steps, n_steps = None, 0
    print(f"    계단 {n_steps:,}건")

    print("[4/4] 저장")
    g_path = RAW / f"osm_{tag}_walk_{TODAY}.graphml"
    e_path = RAW / f"osm_{tag}_edges_{TODAY}.gpkg"
    ox.save_graphml(G, filepath=g_path)          # 원본 그래프는 WGS84로 보존
    edges.reset_index().to_file(e_path, layer="edges", driver="GPKG")
    nodes.reset_index().to_file(e_path, layer="nodes", driver="GPKG")
    if steps is not None and n_steps:
        s_path = RAW / f"osm_{tag}_steps_{TODAY}.gpkg"
        steps.reset_index()[["geometry"]].to_file(s_path, driver="GPKG")
    print(f"    {g_path.name}\n    {e_path.name}")

    # ── 구간 2 회의에 가져갈 실측값 ───────────────────────────
    # MultiDiGraph는 양방향 도로를 두 번 담는다. 구간 통계는 무향 기준으로 낸다.
    import numpy as np
    ei = edges.reset_index()[["u", "v", "key"]]
    seen, keep = set(), []
    for u, v, k in ei.itertuples(index=False):
        key = (min(u, v), max(u, v), k)
        keep.append(key not in seen)
        seen.add(key)
    keep = np.array(keep)
    L = edges["length_m"][keep]
    q = {f"p{p}": round(float(L.quantile(p / 100)), 1) for p in (5, 25, 50, 75, 90, 95, 99)}
    stats = {
        "대상": tag,
        "기준일": TODAY,
        "행정동수": int(len(gdf)),
        "노드수": int(G.number_of_nodes()),
        "방향엣지수": int(G.number_of_edges()),
        "무향구간수": int(keep.sum()),
        "계단수": int(n_steps),
        "구간길이_m": {"최소": round(float(L.min()), 1), "평균": round(float(L.mean()), 1),
                    "최대": round(float(L.max()), 1), **q},
        "짧은구간비율": {
            "20m미만": round(float((L < 20).mean()), 4),
            "50m미만": round(float((L < 50).mean()), 4),
            "100m미만": round(float((L < 100).mean()), 4),
        },
        "총연장_km": round(float(L.sum()) / 1000, 1),
    }
    p = RAW / f"osm_{tag}_stats_{TODAY}.json"
    p.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 56)
    print("구간 2 회의용 실측값 — 이 화면을 그대로 공유하면 된다")
    print("=" * 56)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print("\n판단 기준 (기획서 v3 5.1)")
    print(f"  구간 길이 중앙값 {stats['구간길이_m']['p50']} m")
    print(f"  50m 미만 구간 비율 {stats['짧은구간비율']['50m미만']:.1%}")
    print("  중앙값이 수십 m로 지나치게 잘면 인접 구간 병합 또는 100m 격자로 후퇴한다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
