# busan-subsidence (BigDataComp)

부산 지반침하(싱크홀) 분석 프로젝트. 19일 · 4명.

## 폴더 구조

```
busan-subsidence/
├─ data/              (Git에 안 올림 — 구글드라이브 공유폴더에 같은 구조로)
│  ├─ raw/            원본 그대로. 절대 수정하지 않는다
│  ├─ interim/        전처리 중간 산출
│  └─ processed/      분석에 바로 쓰는 최종본
├─ src/               재사용 코드
├─ notebooks/         탐색용
├─ outputs/
│  ├─ maps/           지도 이미지
│  └─ tables/         보고서에 넣을 표
└─ docs/              보고서 원고
```

## 규칙

| 항목 | 규칙 |
|------|------|
| 코드 | GitHub 비공개 저장소. 커밋 메시지는 한글로 짧게. |
| 데이터 | 용량이 커서 Git에 안 올린다. 구글드라이브 공유폴더에 같은 구조로 둔다. `.gitignore`에 `data/` 추가됨. |
| 파일명 | `{출처}_{내용}_{날짜}.{확장자}` 예: `jis_sinkhole_busan_20260902.csv` |
| 좌표계 | **EPSG:5187 (동부원점 TM)** 으로 통일. 부산은 동경 129도 부근이라 중부원점(5186)이 아니라 동부원점이다. 전국 데이터와 붙일 때만 EPSG:5179(UTM-K)를 경유한다. |
| 진행 공유 | 매일 밤 카톡에 세 줄: 오늘 한 것 / 막힌 것 / 내일 할 것. |

## 분석 환경

python 3.11. 패키지 버전은 `requirements.txt`로 고정.

```bash
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

QGIS도 깔아둔다. 좌표계가 어긋났을 때 눈으로 확인하는 게 가장 빠르다.

환경 확인은 `notebooks/00_env_setup.ipynb` 를 위에서부터 실행. 전부 통과하면 준비 끝.

## 데이터 수집 (구간 1)

- JIS 지반침하 이력: `src/fetch_jis_sinkhole.py` — 활용가이드 v1.4 명세 반영 완료.
  `--test`로 시험 호출 → 기본 실행으로 전국 리스트 수집 후 부산 필터 + 상세 병합.
  필드 정리는 `docs/05_jis_field_memo.md`
- 지오코딩: `src/geocode.py` (API 응답에 위경도가 없어서 필수. 카카오 REST 키 필요)
  `python src/geocode.py data/raw/jis_sinkhole_busan_YYYYMMDD.csv --addr-col full_addr`
- 문의 메일 초안: `docs/01_contact_email_draft.md`
- GPR·오픈랩 체크리스트: `docs/02_gpr_openlab_checklist.md`
- 하수관로·강우·DEM 소스 정리: `docs/03_data_sources_checklist.md`
- 진행 공유 템플릿: `docs/04_daily_share_template.md`

API 키는 `.env` 파일에 넣는다 (Git에 안 올라감):

```
DATA_GO_KR_KEY=발급받은_일반인증키(Decoding)
KAKAO_REST_KEY=카카오_REST_API_키
```
