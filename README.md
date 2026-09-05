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

---

## 구간 1 산출물 — 지훈 (하수관로·강우·DEM / 도로망·행정경계)

WBS 지정 5건 전부 확보 완료. 원본은 Git에 없다 → `docs/06_구간1_원본데이터_목록.md`
(출처·크기·SHA-256·이용조건). 재현 절차는 `docs/인수인계_20260905/04_데이터_재현방법.md`.

| 자료 | 결과 | 핵심 제약 |
|---|---|---|
| 하수관로 | WBS 지정 3소스 전부 부적합 → **부산 하수맨홀 100,646행**으로 대체 | **좌표 컬럼 없음. 최소 공간단위 행정동 206개.** 관경 컬럼 없음 |
| 강우 | 기상청 AWS 시간자료 108개 CSV, 15지점 | 2021년 이후 유효 13지점. 904 사상 지점이 2020-10 3.7 km 이설 |
| DEM | Copernicus GLO-30 (국내 DEM은 국외반출 제한으로 불가) | DSM이라 건물·수목 혼입. 픽셀 25.3 × 30.8 m |
| 도로망 | OSM walk — 무향 구간 **84,066**, 노드 58,752, 계단 588 | 구간 중앙값 55.6 m, 20 m 미만이 19.3% |
| 행정경계 | SGIS 행정동 **206개** | — |

### 분석 단위가 아직 확정되지 않았다

WBS가 "9월 3일 저녁 전원 30분"으로 지정한 회의가 아직 열리지 않았고,
**구간 2 코드 전체가 여기에 달려 있다.** 판단 게이트에 실측값을 대입하면
②(하수관로가 행정동 단위)와 ③(JIS 좌표가 번지 수준)이 걸린다.
근거와 안건은 `docs/분석단위_결정근거.md` — **확정 문서가 아니라 회의 자료다.**

### 코드

| 파일 | 내용 |
|---|---|
| `src/config.py` | 경로·좌표계(기존) + P 가중치·Tobler 상수·검증 파라미터·금지표현(구간1 병합) |
| `src/scoring.py` | `pct` 백분위 정규화, `build_P`, `build_V`, `score`, `sensitivity`, `variable_influence` |
| `src/slope.py` | `walking_speed_kmh`, `travel_minutes`, `slope_from_elevation`, `apply_step_penalty` |
| `src/validation.py` | `capture_rate`, `random_baseline`, `compare_baselines`, `spatial_block_cv`, `check_banned_phrases` |
| `src/osm_extract.py` | OSM 추출 스크립트 |
| `00_setup.py` | 환경·좌표계 검산 (부산시청 → x 206,886 / y 287,023) |

전부 **분석 단위에 의존하지 않게** 작성돼 있다. 도로구간이든 격자든 그대로 쓴다.

### 산출 테이블

`outputs/tables/` — `aws_지점연도_강우요약.csv`(108행), `aws_지점정보_부산15.csv`(15행),
`행정동별_관로노후도.csv`(202행), `구군별_관로노후도.csv`(17행)

> **주의**: 맨홀 `설치일자`는 매설 시점이 아니라 전산 등록 시점으로 의심된다
> (12-31이 13.1%, 01-01이 10.3%). P항 가중치 0.45가 이 변수 위에 서 있으므로
> JIS 151건으로 case-control 검증을 통과해야 한다. 근거는 `docs/전처리_검증_기록.md`.

### 인수인계

`docs/인수인계_20260905/` 9개 문서. 읽는 순서는 `00_먼저_읽기.md`.
미해결·블로커는 `06_미해결과_블로커.md`.
