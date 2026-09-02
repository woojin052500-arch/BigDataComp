"""주소 → 위경도 지오코딩 (JIS 응답에 좌표가 없어서 필수).

카카오 로컬 REST API 사용. https://developers.kakao.com 에서 앱 만들고
REST API 키를 .env 에 KAKAO_REST_KEY= 로 저장 (카카오맵 활성화 ON 필수).

실행:
  python src/geocode.py data/raw/jis_sinkhole_busan_20260902.csv

주소가 "좌동순환로 419 앞" 처럼 시도·시군구 없이 오고 "앞/인근" 같은 꼬리말이
붙어 있어서, 그대로 조회하면 다른 도시가 잡히거나 실패한다. 그래서
  ① 시도+시군구를 반드시 앞에 붙이고
  ② 꼬리말을 떼면서 여러 후보를 순서대로 시도하고
  ③ 도로명주소 조회가 실패하면 키워드(장소) 조회로 한 번 더 시도하고
  ④ 결과가 부산 범위 밖이면 버린다.

산출물:
  data/interim/{입력파일명}_geocoded.csv
  추가 컬럼: lon, lat, x_5187, y_5187, geo_query(실제 성공한 질의),
             geo_method(address/keyword), geo_level(정확도 추정)
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path

import requests

from config import DATA_INTERIM, ROOT, pick

KAKAO_ADDR_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

# 부산 경계 넉넉히 (경도 min/max, 위도 min/max). 이 밖이면 다른 도시가 잡힌 것
BUSAN_BBOX = (128.70, 129.40, 34.85, 35.45)

# 주소 끝에 붙는 위치 서술 — 지오코딩을 방해하므로 떼어낸다
TAIL_WORDS = (
    "앞", "옆", "뒤", "인근", "부근", "일원", "일대", "주변", "앞 도로", "앞도로",
    "이면도로", "교차로", "사거리", "삼거리", "진입로", "입구", "횡단보도", "정류장",
    "버스정류장", "일부구간", "구간", "노상", "도로",
)


def clean(text: str) -> str:
    """괄호 내용·꼬리말 제거 후 공백 정리."""
    t = re.sub(r"\([^)]*\)", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip(" ,.-")
    changed = True
    while changed:  # "419 앞 도로" 처럼 겹쳐 붙은 경우까지 반복해서 제거
        changed = False
        for w in TAIL_WORDS:
            if t.endswith(" " + w) or t == w:
                t = t[: -len(w)].strip(" ,.-")
                changed = True
    return t


def build_candidates(row: dict) -> list[str]:
    """정확한 것부터 느슨한 것 순으로 질의 후보를 만든다."""
    sido = pick(row, "sido", "siDo", "ctprvnNm") or "부산광역시"
    sigungu = pick(row, "sigungu", "siGunGu", "signguNm")
    dong = pick(row, "dong", "emdNm")
    addr = pick(row, "addr", "adres", "rnAddr")
    head = " ".join(p for p in (sido, sigungu) if p)

    addr_clean = clean(addr)
    # 번지/건물번호까지만 남긴 형태 ("좌동순환로 419 앞" → "좌동순환로 419")
    m = re.match(r"^(.*?\d+(?:-\d+)?)", addr_clean)
    addr_num = m.group(1).strip() if m else addr_clean
    # 도로명/동만 남긴 형태 ("좌동순환로 419" → "좌동순환로")
    addr_road = re.sub(r"\s*\d+(-\d+)?.*$", "", addr_clean).strip()

    cands = [
        f"{head} {dong} {addr_num}",
        f"{head} {addr_num}",
        f"{head} {dong} {addr_road}",
        f"{head} {addr_road}",
        f"{head} {dong}",
        head,
    ]
    out: list[str] = []
    for c in cands:
        c = re.sub(r"\s+", " ", c).strip()
        if c and c not in out:
            out.append(c)
    return out


def in_busan(lon: float, lat: float) -> bool:
    lo_min, lo_max, la_min, la_max = BUSAN_BBOX
    return lo_min <= lon <= lo_max and la_min <= lat <= la_max


def search(session: requests.Session, key: str, url: str, query: str):
    r = session.get(
        url,
        params={"query": query, "size": 5},
        headers={"Authorization": f"KakaoAK {key}"},
        timeout=15,
    )
    if r.status_code == 401:
        sys.exit("카카오 인증 실패(401) — REST API 키가 맞는지, 카카오맵이 활성화됐는지 확인")
    r.raise_for_status()
    for d in r.json().get("documents", []):
        try:
            lon, lat = float(d["x"]), float(d["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if in_busan(lon, lat):  # 부산 밖 동명이 도로는 버린다
            return lon, lat
    return None


def geocode_row(session: requests.Session, key: str, row: dict):
    """후보를 순서대로 시도. (lon, lat, 쓴질의, 방법, 정확도) 또는 None."""
    cands = build_candidates(row)
    for level, q in enumerate(cands):
        for url, method in ((KAKAO_ADDR_URL, "address"), (KAKAO_KEYWORD_URL, "keyword")):
            try:
                hit = search(session, key, url, q)
            except requests.RequestException as e:
                print(f"  요청 실패({q}): {e}")
                hit = None
            time.sleep(0.05)  # 쿼터 예의
            if hit:
                # level 0~1은 번지까지, 2~3은 도로/동 수준, 그 이후는 대략 위치
                acc = "번지" if level <= 1 else ("도로/동" if level <= 4 else "시군구")
                return hit[0], hit[1], q, method, acc
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_csv")
    ap.add_argument(
        "--addr-col",
        default=None,
        help="(선택) 이 컬럼값을 상세주소로 우선 사용. 기본은 시도+시군구+읍면동+주소 자동 조립",
    )
    args = ap.parse_args()

    key = env_key()
    src_path = Path(args.input_csv)
    with open(src_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit(f"{src_path} 에 데이터가 없다.")

    # --addr-col 을 준 경우, 그 값을 addr 자리에 끼워 넣고 시도/시군구는 항상 앞에 붙인다
    if args.addr_col:
        if args.addr_col not in rows[0]:
            sys.exit(f"'{args.addr_col}' 컬럼이 없다. 실제 컬럼: {list(rows[0].keys())}")
        for r in rows:
            if (r.get(args.addr_col) or "").strip():
                r["addr"] = r[args.addr_col]

    print(f"질의 예시: {build_candidates(rows[0])[:3]}")

    session = requests.Session()
    ok = fail = 0
    by_acc: dict[str, int] = {}
    for i, row in enumerate(rows, 1):
        res = geocode_row(session, key, row)
        if res:
            lon, lat, q, method, acc = res
            row["lon"], row["lat"] = lon, lat
            row["geo_query"], row["geo_method"], row["geo_level"] = q, method, acc
            by_acc[acc] = by_acc.get(acc, 0) + 1
            ok += 1
        else:
            row["lon"] = row["lat"] = ""
            row["geo_query"] = build_candidates(row)[0]
            row["geo_method"] = row["geo_level"] = "실패"
            fail += 1
        if i % 25 == 0 or i == len(rows):
            print(f"  {i}/{len(rows)} (성공 {ok} / 실패 {fail})")

    print(f"\n지오코딩 성공 {ok} / 실패 {fail}")
    print(f"정확도 분포: {by_acc}  ← '번지'가 많을수록 좋다")

    # EPSG:5187 (동부원점 TM) 좌표 추가 — 프로젝트 표준 좌표계
    try:
        from pyproj import Transformer

        tf = Transformer.from_crs("EPSG:4326", "EPSG:5187", always_xy=True)
    except ImportError:
        tf = None
        print("(pyproj 미설치 — 위경도만 저장. pip install pyproj 후 다시 돌리면 5187 좌표가 붙는다)")

    for row in rows:
        if tf and row["lon"]:
            x, y = tf.transform(float(row["lon"]), float(row["lat"]))
            row["x_5187"], row["y_5187"] = round(x, 2), round(y, 2)
        else:
            row["x_5187"] = row["y_5187"] = ""

    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    DATA_INTERIM.mkdir(parents=True, exist_ok=True)
    out = DATA_INTERIM / f"{src_path.stem}_geocoded.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"저장 완료: {out.relative_to(ROOT)}")
    print("QGIS나 folium으로 점을 찍어서 부산 안에 제대로 들어갔는지 눈으로 확인할 것")


def env_key() -> str:
    from config import env

    key = env("KAKAO_REST_KEY")
    if not key:
        sys.exit("KAKAO_REST_KEY 가 없다. .env 파일에 카카오 REST 키를 넣을 것")
    return key


if __name__ == "__main__":
    main()
