"""프로젝트 공통 설정. 경로·좌표계는 전부 여기서 가져다 쓴다."""
from pathlib import Path

# 이 파일 기준으로 프로젝트 루트를 잡는다 (어디서 실행해도 동일)
ROOT = Path(__file__).resolve().parent.parent

DATA_RAW = ROOT / "data" / "raw"
DATA_INTERIM = ROOT / "data" / "interim"
DATA_PROCESSED = ROOT / "data" / "processed"
OUT_MAPS = ROOT / "outputs" / "maps"
OUT_TABLES = ROOT / "outputs" / "tables"

# 좌표계 규칙: 부산은 동경 129도 부근 → 동부원점 TM. 중부원점(5186) 아님.
CRS_PROJECT = "EPSG:5187"   # 동부원점 TM — 프로젝트 표준
CRS_NATIONAL = "EPSG:5179"  # UTM-K — 전국 데이터와 붙일 때만 경유
CRS_WGS84 = "EPSG:4326"     # API가 주는 위경도

# 부산 시도 코드/명칭 (API 필터·검증용)
BUSAN_SIDO_CODE = "26"
BUSAN_SIDO_NAME = "부산광역시"


def pick(row: dict, *names: str) -> str:
    """대소문자·언더스코어 차이를 무시하고 필드값을 꺼낸다.

    API 응답 필드명이 활용가이드와 다르게 온다 (가이드 siDo → 실제 sido).
    """
    want = [n.lower().replace("_", "") for n in names]
    for k, v in row.items():
        if k.lower().replace("_", "") in want:
            return str(v or "").strip()
    return ""


def build_full_addr(row: dict) -> str:
    """시도+시군구+읍면동+상세주소를 이어 붙인다 (지오코딩 입력용)."""
    parts = [
        pick(row, "sido", "siDo", "ctprvnNm"),
        pick(row, "sigungu", "siGunGu", "signguNm"),
        pick(row, "dong", "emdNm", "eupmyeondong"),
        pick(row, "addr", "adres", "rnAddr", "detailAddr"),
    ]
    return " ".join(p for p in parts if p).strip()


def env(key: str, default: str | None = None) -> str | None:
    """`.env` 파일 또는 환경변수에서 값을 읽는다. python-dotenv 없이 동작."""
    import os

    if key in os.environ:
        return os.environ[key]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip()
    return default

# ═══════════════════════════════════════════════════════
# 이하 구간 1(지훈) 병합분 — 분석 상수
# 위쪽 이름과의 대응:  CRS_PROJECT ≡ CRS_WORK,  DATA_RAW ≡ RAW  …
# 두 이름 모두 살려 두어 기존 코드가 그대로 동작한다.
# ═══════════════════════════════════════════════════════

RAW, INTERIM, PROCESSED = DATA_RAW, DATA_INTERIM, DATA_PROCESSED
MAPS, TABLES = OUT_MAPS, OUT_TABLES
DOCS = ROOT / "docs"

CRS_WORK = CRS_PROJECT      # "EPSG:5187"
CRS_UTMK = CRS_NATIONAL     # "EPSG:5179"

# ── P항 가중치 ──────────────────────────────────────────
# 전국 지반침하 1,433건의 원인별 비율에서 가져온 값이다.
# 임의로 정한 값이 아니며, 보고서에 이 출처를 반드시 적는다.
#   하수관 손상 645건 = 45%  /  되메우기 불량 253 + 굴착공사 부실 111 = 약 25%
#   강우: 6~8월에 46.8% 집중, 8월 단독 19.3%
#   나머지(관경·지질·매립)는 통계상 직접 근거가 없는 탐색 변수
P_WEIGHTS = {
    "pipe_age":   0.45,   # 관로 노후도 — 평균 매설연수, 30년 이상 노후관 비율
    "excavation": 0.25,   # 굴착·공사 이력 — 대심도·도시철도 공사 구간과의 거리, 이력 밀도
    "rain":       0.20,   # 누적 강우 — 연평균 강우, 시간당 30mm 이상 호우 횟수
    "etc":        0.10,   # 관경·지질·매립 — 근거 약함. 뺐을 때와 비교 후 존치 결정
}
assert abs(sum(P_WEIGHTS.values()) - 1.0) < 1e-9

# V항은 원인별 통계 같은 근거가 없으므로 동일 가중을 기본으로 하고,
# 가중치를 바꿔가며 결과가 흔들리는 정도를 본다.
V_KEYS = ["elderly", "delta_time", "sole_route", "shelter_access"]

# ── 경사 보정 보행속도 ──────────────────────────────────
# Tobler hiking function은 연령별 모델이 아니다. 경사에 따라 속도가 떨어지는
# '모양'만 Tobler를 쓰고, 평지 기준속도 ALPHA만 연령에 맞게 낮춘다.
# 원식의 6.0km/h는 성인의 빠른 보행에 가깝다.
# Bohannon(1997) 20~79세 편안한 보행속도: 40대 남성 146.2cm/s ~ 70대 여성 127.2cm/s.
# 70대 여성 기준을 km/h로 바꾸면 약 4.6km/h.
ALPHA_KMH = 4.6
TOBLER_K = 3.5          # 감쇠 계수
TOBLER_OFFSET = 0.05    # 최대 속도가 나오는 하향 경사

# 결과를 '70대의 실제 도달시간'이라 부르지 않는다.
# 70대 평지 보행속도를 기준으로 정규화한 '상대 도달시간'이다.
TIME_LABEL = "상대 도달시간(70대 평지 보행속도 기준)"

# ── 검증 ────────────────────────────────────────────────
TOP_K_PERCENTS = [5, 10, 20]    # 상위 K% 포착률을 재는 지점
N_TOP_SEGMENTS = 30             # 최종 제시할 우선순위 구간 수
RANDOM_BASELINE_ITERS = 100     # 무작위 기준선 반복 횟수
SENSITIVITY_EXPONENTS = [0.5, 0.75, 1.0, 1.5, 2.0]  # P^a x V^b 의 a, b
SIM_TOP_N = 1000                # 도로 차단 시뮬레이션 대상. 감당 안 되면 300으로

# ── 표현 통제 ───────────────────────────────────────────
# 아래 표현은 결과물에 쓰지 않는다. 구간 6 교차검토에서 검색해 확인한다.
BANNED_PHRASES = ["예측", "몇 배", "확률로", "정확도"]
DISCLAIMER = (
    "P와 V, 그리고 둘을 곱한 값은 확률이 아니다. 어떤 구간의 P가 0.8이라는 것은 "
    "침하 발생 확률이 80%라는 뜻이 아니라, 부산의 모든 구간을 줄 세웠을 때 "
    "위험 요인이 상위 20% 안에 든다는 뜻이다. 따라서 이 점수는 부산 안에서 "
    "구간끼리 비교할 때만 의미가 있으며, 다른 도시와 비교할 수 없고 "
    "절대적인 안전 여부를 판정하지 않는다."
)
