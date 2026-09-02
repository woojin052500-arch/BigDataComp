# 남은 작업 상세 가이드 (이 문서만 보고 따라하면 됨)

순서대로 하면 된다. 예상 소요: 1~2단계 30분, 3단계 20분, 나머지는 대기시간 포함 반나절.

---

## 1. PC 환경 준비 + 수집 스크립트 실행 (가장 먼저, 오늘)

### 1-1. 파이썬 3.11 설치 확인

Windows 기준. 명령 프롬프트(cmd)를 열고:

```
python --version
```

- `Python 3.11.x` 가 나오면 통과.
- 없거나 다른 버전이면: https://www.python.org/downloads/ 에서 **3.11.9** 설치.
  설치 첫 화면에서 **"Add python.exe to PATH" 체크박스를 반드시 체크**하고 Install.
  설치 후 cmd를 **새로 열고** 다시 `python --version`.

### 1-2. 프로젝트 폴더 만들기

1. 받은 `busan-subsidence.zip`을 **바탕화면**에 압축 해제 (우클릭 → 압축 풀기)
2. 폴더 이름이 `busan-subsidence`가 되도록 한다 (압축 프로그램에 따라 한 겹 더 생기면 안쪽 폴더를 꺼낸다 — 폴더 안에 바로 `README.md`, `src`, `docs`가 보여야 정상)

### 1-3. 가상환경 + 패키지 설치

cmd에서 (한 줄씩 입력하고 엔터):

```
cd %USERPROFILE%\Desktop\busan-subsidence
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

- `(.venv)` 가 프롬프트 앞에 붙으면 가상환경 활성화된 것.
- 설치는 5~10분 걸린다. 에러 나면 에러 메시지 전체를 복사해서 물어볼 것.
- macOS/리눅스면: `source .venv/bin/activate`

### 1-4. 시험 호출 (③번 단계)

인증키는 이미 `.env` 파일에 들어 있다. 그대로:

```
python src\fetch_jis_sinkhole.py --test
```

**성공하면**: "시험 호출 성공"과 2019년 사고 샘플 5건이 출력된다.

**실패 케이스별 대처**:

| 에러 메시지 | 원인 | 대처 |
|---|---|---|
| `SERVICE_KEY_IS_NOT_REGISTERED` | 활용신청 승인 전이거나 키 오타 | data.go.kr 마이페이지 → 활용신청 상태 확인. 승인까지 최대 1시간 |
| `LIMITED_NUMBER_OF_SERVICE_REQUESTS...` | 일일 트래픽 초과 | 다음날 재시도 |
| `404` 두 번 다 실패 | 엔드포인트 변경 | 포털의 활용가이드 최신판에서 URL 확인 후 `src/fetch_jis_sinkhole.py` 상단 `BASE_URLS` 수정 |
| `ModuleNotFoundError: requests` | 가상환경 비활성 | `.venv\Scripts\activate` 다시 실행 |

### 1-5. 전체 수집 (④번 단계)

```
python src\fetch_jis_sinkhole.py
```

- 2014년~오늘까지 연도별로 전국 리스트를 받고, 부산만 걸러서 상세정보까지 병합한다. 10~30분.
- 끝나면 생기는 파일:
  - `data\raw\jis_sinkhole_busan_20260902.csv` ← **구간 1 핵심 산출물**
  - `data\raw\jis_sinkhole_all_20260902.csv` (전국 원본, 비교용)
- CSV를 엑셀로 열어서 훑어보고, `docs\05_jis_field_memo.md`(필드 설명)와 함께 카톡에 공유.

---

## 2. GitHub 비공개 저장소에 올리기 (본인 계정으로)

### 2-1. 저장소 만들기

1. github.com 로그인 → 우상단 `+` → **New repository**
2. Repository name: `busan-subsidence`
3. **Private** 선택 (중요 — 대회 규칙)
4. "Add a README" 등 체크박스는 **전부 체크 해제** → Create repository

### 2-2. Git 설치 + 내 이름 설정

- Git 없으면 https://git-scm.com/download/win 설치 (전부 기본값 Next).
- cmd 새로 열고, **커밋에 찍힐 본인 이름/이메일** 설정 (이걸 해야 커밋한 사람이 본인으로 뜬다):

```
git config --global user.name "본인깃허브아이디"
git config --global user.email "깃허브에 등록한 이메일"
```

### 2-3. 올리기

```
cd %USERPROFILE%\Desktop\busan-subsidence
git init
git add .
git commit -m "프로젝트 초기 세팅"
git branch -M main
git remote add origin https://github.com/본인아이디/busan-subsidence.git
git push -u origin main
```

- push 때 로그인 창이 뜨면 브라우저로 GitHub 인증.
- `.env`(인증키)와 `data/` 폴더는 `.gitignore` 때문에 **자동으로 제외**된다. 정상이다.
- 팀원 초대: 저장소 페이지 → Settings → Collaborators → Add people.

---

## 3. 위경도 붙이기 (지오코딩 — 카카오 키 필요)

API 응답에 좌표가 없어서 필수다.

### 3-1. 카카오 REST API 키 발급 (5분, 무료)

1. https://developers.kakao.com 접속 → 카카오계정 로그인
2. 상단 **내 애플리케이션** → **애플리케이션 추가하기**
   - 앱 이름: `busan-subsidence` / 회사명: 아무거나(팀명) → 저장
3. 만든 앱 클릭 → 좌측 **앱 설정 > 앱 키** → **REST API 키** 복사
4. 좌측 **제품 설정 > 카카오맵** 들어가서 **활성화 설정 ON** (이거 안 켜면 호출이 거부된다)

### 3-2. 키 넣고 실행

1. `busan-subsidence` 폴더의 `.env` 파일을 메모장으로 열어 `KAKAO_REST_KEY=` 뒤에 복사한 키 붙여넣기, 저장
2. cmd에서 (가상환경 활성 상태로, 파일명의 날짜는 실제 생긴 파일에 맞춤):

```
python src\geocode.py data\raw\jis_sinkhole_busan_20260902.csv --addr-col full_addr
```

3. 결과: `data\interim\jis_sinkhole_busan_20260902_geocoded.csv`
   - `lon`/`lat`(위경도) + `x_5187`/`y_5187`(프로젝트 표준좌표) 컬럼이 붙어 나온다
   - "성공 N / 실패 M" 출력에서 실패분은 주소가 부실한 건들 — 몇 건인지 카톡에 공유

---

## 4. 대회 사무국 메일 보내기

1. `docs\01_contact_email_draft.md` 를 연다
2. 제목/본문을 그대로 복사 → 메일로 ask@dxchallenge.co.kr 에 발송
   - 마지막 줄 "○○팀 드림 (연락처)"만 실제 팀명/전화번호로 바꾼다
3. **오전에 발송**하고, 당일 오후까지 답 없으면 대회 공고문(모집요강 하단)에서 전화번호 찾아 전화
4. 답변 오면 스크린샷 그대로 카톡 공유

---

## 5. GPR 페이지 + 데이터 오픈랩 (전화 필요)

`docs\02_gpr_openlab_checklist.md` 를 열고 체크박스 순서대로. 요점만:

- **GPR 페이지** (https://www.busan.go.kr/depart/GPR): PC 크롬에서 열어본다. 에러면 부산시 홈페이지 통합검색에 "GPR", "지반탐사" 검색으로 우회. 탐사 구간·공동 발견 현황 파일이 있으면 다운로드해서 `data\raw\`에 저장.
- **오픈랩** (https://busanbigdata.kr/): 사이트 하단 대표번호로 전화해서 4가지를 묻는다 — ①일반 참가팀 방문 가능? ②예약 절차? ③열람 가능 데이터 목록(지반침하/도로/상하수도 관련 있는지)? ④분석 결과물 반출 조건?
- 통화 내용은 체크리스트 하단 메모 표에 적고, **"GPR 확보: 가능/부분/불가"** 판정과 **방문 가능자(누가, 언제)** 를 카톡으로 확정.

---

## 6. 하수관로·강우·DEM (지훈님 몫)

`docs\03_data_sources_checklist.md` 에 어디서 뭘 받는지 정리돼 있다. 요약:

- **하수관로**: data.go.kr에서 "부산광역시 하수관로" 검색 → SHP/CSV 다운로드. **매설년도 컬럼이 있는지** 먼저 확인
- **강우**: data.kma.go.kr → 기상자료개방포털 → ASOS 시간자료 → 지점 **159(부산)**, 기간 2014~현재 → CSV 다운로드
- **DEM**: map.ngii.go.kr → 수치표고모형 → 부산 지역 90m부터 (5m는 활용신청 필요)
- 전부 `data\raw\` 에 규칙대로 저장: `{출처}_{내용}_{날짜}.{확장자}`

---

## 7. 구글드라이브 + 마무리

1. 구글드라이브에 공유폴더 `busan-subsidence-data` 생성 → 팀원 4명 편집자로 초대
2. 안에 `raw / interim / processed` 폴더를 만들고 PC의 `data\` 내용 업로드 (Git에는 데이터가 안 올라가므로 이게 팀 공유 경로다)
3. 팀원 각자: 저장소 clone → 1-3처럼 가상환경 만들고 → `notebooks\00_env_setup.ipynb` 실행 (`pip install jupyterlab` 은 requirements에 포함됨, `jupyter lab` 으로 실행) → 전부 통과하면 카톡에 "환경 OK"
4. 매일 밤 카톡 세 줄 (`docs\04_daily_share_template.md` 양식)

---

## 막히면 규칙 (사진 문서 그대로)

- JIS 수집이 **9/2까지 안 되면 언론보도 수집으로 전환**한다. 분석 일정은 건드리지 않는다.
- 에러가 나면 혼자 30분 이상 붙잡지 말고 에러 화면을 그대로 공유할 것.
