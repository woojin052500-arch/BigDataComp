"""JIS 지반침하사고 이력 수집 — 국토교통부_지하안전정보 OPEN API (활용가이드 v1.4 반영).

포털: https://www.data.go.kr/data/15041891/openapi.do
지도 확인: https://www.jis.go.kr/

오퍼레이션 (가이드 v1.4):
  MOLITJIS-12 getSubsidenceList01  지반침하사고 리스트 (sagoDateFrom/To 필수)
  MOLITJIS-13 getSubsidenceInfo01  지반침하사고 정보   (sagoNo로 상세 조회)

주의 — 실행으로 확인된 사실 (2026-09-02):
  * 시도 필터 파라미터가 없다 → 전국을 받아서 시도값으로 걸러낸다 (부산 151/전국 1648건)
  * 응답 필드명이 가이드와 다르다: siDo→sido, siGunGu→sigungu, sagoDetail→sagoReason
    → config.pick / build_full_addr 가 대소문자 무시하고 찾는다
  * totalCount가 항상 0으로 온다 → 페이지가 꽉 차는 동안 계속 요청하는 방식으로 순회
  * 응답에 위경도가 없다 (주소만) → src/geocode.py 로 지오코딩
  * 일자·규모(폭/연장/깊이)·복구상태는 상세 조회(getSubsidenceInfo01)에 들어 있다

사전 준비: .env 에 DATA_GO_KR_KEY=인증키 (Encoding/Decoding 어느 쪽이든 알아서 처리)

실행:
  python src/fetch_jis_sinkhole.py --test                # 1페이지 시험 호출
  python src/fetch_jis_sinkhole.py                       # 2014-01-01 ~ 오늘 전체 수집
  python src/fetch_jis_sinkhole.py --from 2018 --to 2026 # 기간 지정(연도)

산출물:
  data/raw/jis_sinkhole_busan_YYYYMMDD.csv   (부산, 상세정보 병합본)
  data/raw/jis_sinkhole_all_YYYYMMDD.csv     (전국 리스트 원본 — 비교용)
  필드 설명은 docs/05_jis_field_memo.md 참고 (가이드 명세로 미리 작성됨)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import time
import urllib.parse

import requests

from config import DATA_RAW, ROOT, build_full_addr, env

# 포털 페이지는 1613000, 활용가이드 v1.4는 1611000 — 둘 다 시도한다
BASE_URLS = [
    "https://apis.data.go.kr/1613000/undergroundsafetyinfo01",
    "https://apis.data.go.kr/1611000/undergroundsafetyinfo01",
]
NUM_OF_ROWS = 100
_active_base: str | None = None


def get_key() -> str:
    key = env("DATA_GO_KR_KEY")
    if not key:
        sys.exit("DATA_GO_KR_KEY 가 없다. .env 파일에 인증키를 넣을 것 (README 참고)")
    if "%" in key:  # Encoding 키면 Decoding 형태로 되돌린다 (requests가 다시 인코딩함)
        key = urllib.parse.unquote(key)
    return key


def parse_payload(r: requests.Response) -> dict:
    text = r.text.lstrip()
    if text.startswith("{"):
        return r.json()
    # XML 응답 (type=xml이거나 인증키 오류 — 오류는 항상 XML로 온다)
    import xml.etree.ElementTree as ET

    root = ET.fromstring(r.text)
    err = root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg")
    code = root.findtext(".//returnReasonCode")
    if err and (root.findtext(".//resultCode") or "0") not in ("0", "00"):
        raise RuntimeError(f"API 오류: {err} (code={code}) — 인증키/활용신청 상태 확인")
    if err and "SERVICE" in (err or "").upper():
        raise RuntimeError(f"API 오류: {err} (code={code})")
    items = [
        {c.tag: (c.text or "").strip() for c in item} for item in root.iter("item")
    ]
    total = root.findtext(".//totalCount") or "0"
    return {"response": {"body": {"items": {"item": items}, "totalCount": total}}}


def call(operation: str, key: str, **params) -> tuple[list[dict], int]:
    """오퍼레이션 호출. 기관코드 1613000 실패 시 1611000으로 자동 전환."""
    global _active_base
    bases = [_active_base] if _active_base else BASE_URLS
    last_err: Exception | None = None
    for base in bases:
        url = f"{base}/{operation}"
        q = {"serviceKey": key, "type": "json", **params}
        for attempt in range(3):
            try:
                r = requests.get(url, params=q, timeout=30)
                if r.status_code == 404:
                    raise requests.HTTPError(f"404 (기관코드 다름?): {url}")
                r.raise_for_status()
                payload = parse_payload(r)
                _active_base = base
                body = payload.get("response", {}).get("body", {})
                items = body.get("items") or {}
                if isinstance(items, dict):
                    items = items.get("item") or []
                if isinstance(items, dict):  # 1건이면 dict로 오는 경우
                    items = [items]
                total = int(body.get("totalCount") or 0)
                return items, total
            except (requests.RequestException, ValueError) as e:
                last_err = e
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
        print(f"  {base} 실패 → 다음 후보 시도 ({last_err})")
    raise RuntimeError(f"모든 엔드포인트 실패: {last_err}")


def fetch_list(key: str, date_from: str, date_to: str) -> list[dict]:
    """지반침하사고 리스트 전체 페이지 순회 (기간 필수).

    totalCount가 응답에 안 실려 오는 경우가 있어서, 페이지가 꽉 차게(numOfRows)
    돌아오는 동안 계속 다음 페이지를 요청하는 방식으로 순회한다.
    """
    rows: list[dict] = []
    page = 1
    while page <= 500:  # 안전장치
        items, total = call(
            "getSubsidenceList01", key,
            sagoDateFrom=date_from, sagoDateTo=date_to,
            pageNo=page, numOfRows=NUM_OF_ROWS,
        )
        rows.extend(items)
        print(f"  {date_from}~{date_to} p{page}: +{len(items)} (누적 {len(rows)}, totalCount={total})")
        if len(items) < NUM_OF_ROWS:  # 덜 찬 페이지 = 마지막 페이지
            break
        page += 1
        time.sleep(0.2)  # 30tps 제한 예의
    return rows


def sido_value(row: dict) -> str:
    """응답 필드명이 가이드와 달라도 시도 값을 찾아낸다 (siDo/sido/sidoNm/ctprvnNm 등)."""
    for k, v in row.items():
        kl = k.lower().replace("_", "")
        if "sido" in kl or "ctprvn" in kl:
            return str(v or "")
    return ""


def fetch_info(key: str, sago_no: str) -> dict:
    items, _ = call("getSubsidenceInfo01", key, sagoNo=sago_no, pageNo=1, numOfRows=10)
    return items[0] if items else {}


def save_csv(path, rows: list[dict]) -> None:
    cols: list[str] = []
    for r in rows:  # 행마다 컬럼이 다를 수 있어 합집합 사용
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="1페이지만 시험 호출")
    ap.add_argument("--from", dest="year_from", type=int, default=2014)
    ap.add_argument("--to", dest="year_to", type=int, default=dt.date.today().year)
    args = ap.parse_args()

    key = get_key()

    if args.test:
        items, total = call(
            "getSubsidenceList01", key,
            sagoDateFrom="20190101", sagoDateTo="20191231", pageNo=1, numOfRows=5,
        )
        print(f"시험 호출 성공 (endpoint={_active_base})")
        print(f"2019년 전국 사고 totalCount={total}, 샘플:")
        for it in items:
            print(" ", it)
        return

    # 1) 전국 리스트 — 연 단위로 끊어서 수집 (기간 파라미터가 필수라서)
    all_rows: list[dict] = []
    for year in range(args.year_from, args.year_to + 1):
        end = min(dt.date(year, 12, 31), dt.date.today())
        all_rows.extend(fetch_list(key, f"{year}0101", end.strftime("%Y%m%d")))
    print(f"전국 리스트 합계: {len(all_rows)}건")

    today = f"{dt.date.today():%Y%m%d}"
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    save_csv(DATA_RAW / f"jis_sinkhole_all_{today}.csv", all_rows)

    # 2) 부산 필터 → 상세정보 병합
    # 필터 전에 실제 응답 구조를 보여준다 (필드명이 가이드와 다를 수 있어서)
    if all_rows:
        from collections import Counter

        print(f"응답 필드: {list(all_rows[0].keys())}")
        dist = Counter(sido_value(r) for r in all_rows)
        print(f"시도 분포(상위 20): {dict(dist.most_common(20))}")

    busan = [r for r in all_rows if "부산" in sido_value(r)]
    print(f"부산 필터: {len(busan)}건")
    if all_rows and not busan:
        print("!! 부산이 0건 — 위의 '응답 필드'와 '시도 분포', 샘플 1건을 확인할 것:")
        print(f"   샘플: {all_rows[0]}")
    merged: list[dict] = []
    for i, row in enumerate(busan, 1):
        detail = fetch_info(key, str(row.get("sagoNo", "")))
        out = {**row, **detail}
        # 지오코딩용 전체 주소 컬럼 (응답에 위경도가 없다 → src/geocode.py)
        # 필드명이 가이드와 달라서(siDo→sido 등) 대소문자 무시하고 조립한다
        out["full_addr"] = build_full_addr(out)
        out.pop("no", None)
        merged.append(out)
        if i == 1:
            print(f"  상세 응답 필드: {list(detail.keys())}")
            print(f"  주소 조립 예시: {out['full_addr']!r}")
        if i % 20 == 0 or i == len(busan):
            print(f"  상세 조회 {i}/{len(busan)}")
        time.sleep(0.1)

    filled = sum(1 for r in merged if r["full_addr"])
    print(f"주소 조립 완료: {filled}/{len(merged)}건 (지오코딩 가능 건수)")

    out_path = DATA_RAW / f"jis_sinkhole_busan_{today}.csv"
    save_csv(out_path, merged)
    print(f"\n저장 완료: {out_path.relative_to(ROOT)} ({len(merged)}건)")
    print("다음 단계: 위경도가 없으므로 지오코딩 →")
    print(f"  python src/geocode.py {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
