"""
환경 세팅 확인 — 팀 전원이 이 파일을 돌려 같은 출력이 나와야 한다.

  python3 00_setup.py

각자 환경이 다르면 같은 코드가 다르게 돈다.
버전이 requirements.txt와 다르면 아래에서 걸린다.
"""
import sys, importlib

REQUIRED = ["geopandas", "shapely", "pyproj", "rasterio", "osmnx",
            "networkx", "pandas", "numpy", "scipy", "sklearn",
            "matplotlib", "folium", "mapclassify"]

print(f"python {sys.version.split()[0]}\n")
missing = []
for m in REQUIRED:
    try:
        mod = importlib.import_module(m)
        print(f"  OK   {m:<14}{getattr(mod, '__version__', '')}")
    except Exception:
        print(f"  MISS {m}")
        missing.append(m)

if missing:
    print(f"\n설치 필요: pip install {' '.join(missing)}")
    sys.exit(1)

# 좌표계 확인 — 부산이 EPSG:5187 안에서 제대로 잡히는지
from pyproj import Transformer
t = Transformer.from_crs("EPSG:4326", "EPSG:5187", always_xy=True)
x, y = t.transform(129.0756, 35.1796)          # 부산시청
print(f"\n좌표계 확인 (EPSG:5187)")
print(f"  부산시청 129.0756, 35.1796 -> x={x:,.1f} y={y:,.1f}")
assert 150_000 < x < 300_000, "동부원점(5187)이 아닌 것 같다. 중부원점 5186을 쓰고 있지 않은지 확인."
print("  동부원점 정상")

# 자체 모듈 확인
sys.path.insert(0, "src")
from slope import walking_speed_kmh, travel_minutes
from scoring import pct
from config import ALPHA_KMH, P_WEIGHTS

print(f"\n자체 모듈")
print(f"  ALPHA = {ALPHA_KMH} km/h  |  평지 속도 {walking_speed_kmh(0):.2f} km/h")
print(f"  경사 15% 구간 100m 통과 {float(travel_minutes(100, 0.15)):.2f}분")
print(f"  P 가중치 합계 {sum(P_WEIGHTS.values()):.2f}")
print(f"  백분위 정규화 [1,5,3] -> {pct([1,5,3]).round(2).tolist()}")

print("\n환경 정상. 이 출력이 팀원끼리 같아야 한다.")
