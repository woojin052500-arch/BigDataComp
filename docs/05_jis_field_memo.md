# JIS 지반침하사고 데이터 필드 설명 메모

- 출처: 공공데이터포털 국토교통부_지하안전정보 (활용가이드 v1.4)
- 오퍼레이션: `getSubsidenceList01`(리스트) + `getSubsidenceInfo01`(상세) 병합
- 산출 파일: `data/raw/jis_sinkhole_busan_YYYYMMDD.csv` (`src/fetch_jis_sinkhole.py`)

## 필드 (가이드 명세 기준)

| 필드명 | 국문명 | 타입 | 비고 |
|--------|--------|------|------|
| `sagoNo` | 사고번호 | VARCHAR(20) | 상세 조회 키 |
| `siDo` | 시도 | VARCHAR(20) | "부산광역시"로 필터 |
| `siGunGu` | 시군구 | VARCHAR(20) | |
| `dong` | 읍면동 | VARCHAR(50) | 상세에만 있음 |
| `addr` | 상세주소 | VARCHAR(200) | 번지 수준 |
| `sagoDate` | 발생일자 | VARCHAR(8) | YYYYMMDD |
| `sinkWidth` | 발생규모 폭(m) | NUMBER(9,2) | |
| `sinkExtend` | 발생규모 연장(m) | NUMBER(9,2) | |
| `sinkDepth` | 발생규모 깊이(m) | NUMBER(9,2) | |
| `grdKind` | 발생지역 지질종류 | VARCHAR(20) | 옵션(결측 가능) |
| `sagoDetail` | 상세 발생원인 | VARCHAR(2000) | 예: "상수도 파열". 관리원 확인 전엔 "확인중" |
| `deathCnt` | 피해 사망자수 | NUMBER(7) | |
| `injuryCnt` | 피해 부상자수 | NUMBER(7) | |
| `vehicleCnt` | 피해 차량대수 | NUMBER(7) | |
| `trStatus` | 복구상태 | VARCHAR(10) | 예: "완전복구" |
| `trMethod` | 복구방법 | VARCHAR(2000) | 예: "되메움" |
| `trFnDate` | 복구완료일자 | VARCHAR(8) | |
| `daStDate` | 데이터기준일자 | VARCHAR(8) | |
| `full_addr` | (우리가 만든 컬럼) | | siDo+siGunGu+dong+addr 연결 — 지오코딩 입력용 |

## "확인할 것" 판정 (가이드 명세로 확정)

- **부산으로 필터되는가**: X — 시도 요청 파라미터가 없다. 전국 수집 후 `siDo`로 필터 (스크립트가 자동 처리)
- **위경도가 있는가**: X — 주소만 있다 → **카카오 지오코딩 필요** (`src/geocode.py`, `--addr-col full_addr`)
- **발생원인 분류가 있는가**: O — `sagoDetail`. 다만 자유서술이라 분석 시 카테고리화(상수도/하수도/굴착공사/기타) 전처리 필요
- **발생일자·규모·복구여부**: O — `sagoDate`, `sinkWidth/Extend/Depth`, `trStatus/trFnDate`
- **도로 함몰 사고와 GPR 공동 발견 구분**: 이 API는 **사고 이력만** 있다. GPR 공동 발견 현황은 여기 없음 → 부산시 GPR 페이지/오픈랩에서 별도 확보 (`docs/02_gpr_openlab_checklist.md`)

## 기타

- 요청 파라미터: `sagoDateFrom`/`sagoDateTo`(필수, YYYYMMDD), `pageNo`, `numOfRows`
- 엔드포인트: `apis.data.go.kr/1613000/undergroundsafetyinfo01` (포털 표기) — 가이드 v1.4에는 1611000으로 되어 있어 스크립트가 둘 다 시도함
- 호출 제한: 30tps, 트래픽 초과 시 다음날 재시도
