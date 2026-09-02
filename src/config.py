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
