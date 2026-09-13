"""수집·지오코딩 결과 점검 — 지도 1장 + 요약표 4장을 한 번에 만든다.

좌표가 부산에 제대로 찍혔는지 눈으로 확인하고, 보고서에 넣을 기초 통계를 뽑는 용도.

실행:
  python src/quick_check.py data/interim/jis_sinkhole_busan_20260902_geocoded.csv

산출물:
  outputs/maps/busan_sinkhole_points.html   브라우저로 열어서 확인 (연도 색 구분)
  outputs/tables/사고_연도별.csv
  outputs/tables/사고_구군별.csv
  outputs/tables/사고_원인별.csv
  outputs/tables/사고_규모_복구.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from config import OUT_MAPS, OUT_TABLES, ROOT

BUSAN_BBOX = (128.70, 129.40, 34.85, 35.45)  # lon_min, lon_max, lat_min, lat_max

# 자유서술인 sagoReason 을 보고서용 대분류로 묶는다 (키워드 우선순위 순)
CAUSE_RULES = [
    ("상수도", ("상수", "급수", "수도관")),
    ("하수도", ("하수", "우수", "오수", "배수")),
    ("굴착공사", ("굴착", "공사", "터파기", "시공", "흙막이")),
    ("지하구조물", ("지하철", "전력", "통신", "가스", "관로", "맨홀")),
    ("다짐불량", ("다짐", "되메", "뒤채움", "매립")),
    ("자연/지반", ("강우", "호우", "침식", "지하수", "연약")),
]


def classify_cause(text: str) -> str:
    t = str(text or "")
    for label, keys in CAUSE_RULES:
        if any(k in t for k in keys):
            return label
    if not t.strip() or "확인" in t:
        return "확인중/미상"
    return "기타"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_csv")
    args = ap.parse_args()

    path = Path(args.input_csv)
    if not path.exists():
        sys.exit(f"파일이 없다: {path}")
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    print(f"불러옴: {path.name} — {len(df)}행, 컬럼 {len(df.columns)}개")

    for col in ("lon", "lat"):
        if col not in df.columns:
            sys.exit(f"'{col}' 컬럼이 없다. geocode.py 결과 파일을 넣을 것")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 1) 좌표 검증 ---------------------------------------------------------
    no_coord = df["lon"].isna().sum()
    lo_min, lo_max, la_min, la_max = BUSAN_BBOX
    inside = df["lon"].between(lo_min, lo_max) & df["lat"].between(la_min, la_max)
    outside = df[df["lon"].notna() & ~inside]  # 경도·위도 중 하나만 벗어나도 이상값
    print(f"좌표 없음 {no_coord}건 / 부산 범위 밖 {len(outside)}건")
    if len(outside):
        print(outside[["sagoNo", "geo_query", "lon", "lat"]].head(10).to_string(index=False))
    if "geo_level" in df.columns:
        print(f"정확도 분포: {df['geo_level'].value_counts().to_dict()}")

    # 2) 파생 컬럼 ---------------------------------------------------------
    if "sagoDate" not in df.columns:
        sys.exit("'sagoDate' 컬럼이 없다. 수집 원본 CSV가 맞는지 확인할 것")
    date = pd.to_datetime(df["sagoDate"], format="%Y%m%d", errors="coerce")
    df["연도"] = date.dt.year
    df["월"] = date.dt.month
    reason = df["sagoReason"] if "sagoReason" in df.columns else pd.Series([""] * len(df))
    df["원인분류"] = reason.map(classify_cause)
    for c in ("sinkWidth", "sinkExtend", "sinkDepth"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    OUT_MAPS.mkdir(parents=True, exist_ok=True)

    def dump(table: pd.DataFrame, name: str) -> None:
        p = OUT_TABLES / name
        table.to_csv(p, encoding="utf-8-sig")
        print(f"  표 저장: {p.relative_to(ROOT)}")

    # 3) 요약표 -----------------------------------------------------------
    print("\n[연도별]")
    by_year = df.groupby("연도").size().rename("건수").to_frame()
    print(by_year.to_string())
    dump(by_year, "사고_연도별.csv")

    gu_col = "sigungu" if "sigungu" in df.columns else "siGunGu"
    print("\n[구·군별]")
    by_gu = df.groupby(gu_col).size().rename("건수").sort_values(ascending=False).to_frame()
    print(by_gu.to_string())
    dump(by_gu, "사고_구군별.csv")

    print("\n[원인 분류별]")
    by_cause = df.groupby("원인분류").size().rename("건수").sort_values(ascending=False).to_frame()
    print(by_cause.to_string())
    dump(by_cause, "사고_원인별.csv")

    size_cols = [c for c in ("sinkWidth", "sinkExtend", "sinkDepth") if c in df.columns]
    if size_cols:
        print("\n[규모 통계 (m)]")
        stat = df[size_cols].describe().round(2)
        print(stat.to_string())
        dump(stat, "사고_규모_복구.csv")
    if "trStatus" in df.columns:
        print(f"복구상태: {df['trStatus'].value_counts().to_dict()}")

    # 4) 지도 -------------------------------------------------------------
    import folium

    pts = df[df["lon"].notna()]
    m = folium.Map(location=[35.18, 129.07], zoom_start=11, tiles="CartoDB positron")
    years = sorted(y for y in pts["연도"].dropna().unique())
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
               "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    color_of = {y: palette[i % len(palette)] for i, y in enumerate(years)}

    for _, r in pts.iterrows():
        year = r["연도"]
        popup = (
            f"{r.get('sagoNo','')} | {r.get('sagoDate','')}<br>"
            f"{r.get(gu_col,'')} {r.get('geo_query','')}<br>"
            f"원인: {r.get('sagoReason','')}<br>"
            f"규모(W×L×D): {r.get('sinkWidth','')}×{r.get('sinkExtend','')}×{r.get('sinkDepth','')}m<br>"
            f"정확도: {r.get('geo_level','')}"
        )
        folium.CircleMarker(
            location=[r["lat"], r["lon"]],
            radius=5,
            color=color_of.get(year, "#333333"),
            fill=True,
            fill_opacity=0.75,
            popup=folium.Popup(popup, max_width=320),
        ).add_to(m)

    legend = "".join(
        f"<div><span style='display:inline-block;width:10px;height:10px;"
        f"background:{color_of[y]};border-radius:5px;margin-right:6px'></span>{int(y)}</div>"
        for y in years
    )
    m.get_root().html.add_child(
        folium.Element(
            "<div style='position:fixed;bottom:24px;left:24px;z-index:9999;background:#fff;"
            "padding:10px 12px;border:1px solid #999;border-radius:6px;font:12px sans-serif'>"
            f"<b>지반침하 사고 {len(pts)}건</b>{legend}</div>"
        )
    )
    out_map = OUT_MAPS / "busan_sinkhole_points.html"
    m.save(str(out_map))
    print(f"\n지도 저장: {out_map.relative_to(ROOT)} — 브라우저로 열어서 확인할 것")


if __name__ == "__main__":
    main()
