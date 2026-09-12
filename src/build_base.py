"""
구간 2 A단계 — 분석 단위와 무관한 기반 레이어·샘플링 함수

분석 단위(도로 구간 vs 100m 격자)가 확정되기 전에 만들 수 있는 것만 둔다.
여기 있는 함수는 전부 `(x, y)` 좌표 또는 기하를 받아 값을 돌려준다.
단위가 정해지면 B단계에서 단위 객체를 만들어 이 함수들을 호출하기만 하면 된다.

좌표는 모두 EPSG:5187 (동부원점 TM, 미터).
검증 기록은 docs/구간2_A단계_검증.md.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, re

try:
    from config import RAW, INTERIM, TABLES, ROOT, CRS_WORK
except ImportError:                                    # 스크립트로 직접 실행할 때
    ROOT = Path(__file__).resolve().parents[1]
    RAW, INTERIM, TABLES = ROOT/"data"/"raw", ROOT/"data"/"interim", ROOT/"outputs"/"tables"
    CRS_WORK = "EPSG:5187"

EPSG = 5187
_norm = lambda s: re.sub(r"제(\d)", r"\1", str(s))      # 가야제1동 → 가야1동


# ────────────────────────────────────────────────────────────
# 1. 기반 레이어 (data/interim, prep 단계에서 생성)
# ────────────────────────────────────────────────────────────
def load_boundary() -> gpd.GeoDataFrame:
    """행정동 206개. 컬럼 adm_nm, adm_cd, gu, dong(정규화), geometry."""
    return gpd.read_parquet(INTERIM/"admdong.parquet")

def load_edges() -> gpd.GeoDataFrame:
    """부산 경계로 클리핑한 무향 도로 구간 83,839개. seg_id, len_m, name, highway."""
    return gpd.read_parquet(INTERIM/"edges_clipped.parquet")

def load_steps() -> gpd.GeoDataFrame:
    """OSM 계단 피처 598개(선형), 15.6 km.

    주의: 그래프 엣지의 highway 속성으로 세면 588개 30.8 km가 나오는데,
    그중 289개(23.2 km)는 osmnx 단순화로 footway·path와 합쳐진 것이라 과대치다.
    계단 항 입력은 반드시 이 피처 레이어를 쓴다. (docs/구간1_재검토_20260907.md D5)
    """
    return gpd.read_parquet(INTERIM/"steps.parquet")


# ────────────────────────────────────────────────────────────
# 2. 표고 — COP30은 DSM이라 건물·수목이 섞여 있다
# ────────────────────────────────────────────────────────────
class Elevation:
    """분위 필터로 건물·수목을 걷어낸 표고 샘플러.

    window=3 (75 m 창) · pct=25 를 기본으로 쓴다. 검증 결과:
      창3(75m)  급경사 보존 93.8% · 건물 제거 p90 7.8 m
      창5(125m) 급경사 보존 87.7% · 건물 제거 p90 12.6 m
    산복도로 경사가 주제의 핵심이라 보존율이 높은 창3을 택했다.
    """
    def __init__(self, path=None, window: int = 3, pct: int = 25):
        import rasterio
        from scipy.ndimage import percentile_filter
        self.path = Path(path or INTERIM/"dem_5187.tif")
        with rasterio.open(self.path) as d:
            a = d.read(1).astype("float32")
            self.nodata, self.T, self.shape = d.nodata, d.transform, a.shape
        a = np.where(a == self.nodata, np.nan, a)
        self.raw = a
        fill = np.where(np.isnan(a), np.nanmax(a), a)
        self.dtm = percentile_filter(fill, percentile=pct, size=window, mode="nearest")
        self.window, self.pct = window, pct

    def at(self, x, y, filtered: bool = True) -> np.ndarray:
        """좌표 배열 → 표고(m). filtered=False면 원본 DSM."""
        from rasterio.transform import rowcol
        x, y = np.atleast_1d(x), np.atleast_1d(y)
        r, c = rowcol(self.T, x, y)
        r = np.clip(np.asarray(r), 0, self.shape[0]-1)
        c = np.clip(np.asarray(c), 0, self.shape[1]-1)
        return (self.dtm if filtered else self.raw)[r, c]

    def profile(self, geom, step: float = 20.0):
        """선형 기하를 따라 step m 간격 샘플링 → (누적거리, 표고).

        구간 경사는 시·종점 표고차가 아니라 이 표고열의 최소제곱 회귀 기울기로 낸다.
        짧은 구간에서 노이즈가 경사로 둔갑하는 것을 막기 위해서다.
        """
        L = geom.length
        d = np.arange(0, L + step, step) if L > step else np.array([0.0, L])
        pts = [geom.interpolate(t) for t in d]
        return d, self.at([p.x for p in pts], [p.y for p in pts])

    def slope(self, geom, step: float = 20.0, min_len: float = 20.0):
        """구간 경사(rise/run). 길이 min_len 미만이면 NaN.

        20 m 미만 구간은 53.7%가 표고차 0으로 나와 경사를 잴 수 없다
        (DEM 픽셀 25 m). 값을 만들어내지 않고 결측으로 남긴다.
        """
        if geom.length < min_len:
            return np.nan, np.nan
        d, z = self.profile(geom, step)
        if len(d) < 2 or np.all(np.isnan(z)):
            return np.nan, np.nan
        fit = np.polyfit(d, z, 1)[0]
        seg = np.abs(np.diff(z) / np.maximum(np.diff(d), 1e-9))
        return abs(fit), (np.nanmax(seg) if len(seg) else np.nan)


# ────────────────────────────────────────────────────────────
# 3. 강우 — 평면 추세면 (IDW는 검증에서 탈락)
# ────────────────────────────────────────────────────────────
class Rain:
    """AWS 13지점(2021~2025 정상상태)에서 적합한 1차 추세면.

    LOO 교차검증 (기준선 = 전체 평균):
      평면 추세 (1,x,y)   R²  0.169 (연강수) / 0.188 (30mm↑)   ← 채택
      IDW p=1 / p=2 / p=3 R² -0.128 / -0.207 / -0.358          모두 기준선보다 나쁨
      최근접 지점          R² -0.780                            가장 나쁨
      평면+고도            R² -4.024                            13개 표본에 과적합

    R² 0.17은 약하다. 구간 3에서 variable_influence()로 rain을 뺐을 때
    상위 구간이 얼마나 바뀌는지 확인하고 가중치 0.20 유지 여부를 판단한다.
    어느 쪽이든 이 수치를 보고서 3장 한계에 적는다.
    """
    def __init__(self, table=None):
        t = pd.read_csv(table or TABLES/"aws_추세면_계수.csv")
        self.c = {r.변수: np.array([r.절편, r.동서계수, r.남북계수]) for r in t.itertuples()}
        self.x0, self.y0 = t.기준x.iloc[0], t.기준y.iloc[0]
        self.meta = t

    def at(self, x, y) -> pd.DataFrame:
        x, y = np.atleast_1d(x), np.atleast_1d(y)
        A = np.c_[np.ones(len(x)), (x-self.x0)/1000, (y-self.y0)/1000]
        return pd.DataFrame({k: A @ v for k, v in self.c.items()})


# ────────────────────────────────────────────────────────────
# 4. 행정동 귀속과 관로 속성
# ────────────────────────────────────────────────────────────
def dong_of(x, y, boundary=None) -> pd.DataFrame:
    """좌표 → 소속 행정동(gu, dong, adm_cd). 경계 밖이면 결측."""
    sg = boundary if boundary is not None else load_boundary()
    p = gpd.GeoDataFrame(geometry=gpd.points_from_xy(np.atleast_1d(x), np.atleast_1d(y)), crs=EPSG)
    j = gpd.sjoin(p, sg[["gu", "dong", "adm_cd", "geometry"]], how="left", predicate="within")
    return j[~j.index.duplicated()][["gu", "dong", "adm_cd"]].reset_index(drop=True)

def pipe_attrs() -> pd.DataFrame:
    """행정동 206개의 관로 속성. 좌표가 없어 공간조인이 불가능해 속성 조인으로 간다.

    맨홀 자료에 좌표 컬럼이 아예 없어 최소 공간 단위가 행정동이다.
    도로 구간이든 100 m 격자든 이 값은 206개 계단함수다. (결정팩 게이트 ②)
    `설치일자`는 매설 시점이 아니라 전산 등록 시점일 가능성이 높다
    (설치일자==측량일자가 59.8%). JIS 151건으로 검증 후 0.45 유지 여부를 정한다.
    """
    d = pd.read_csv(TABLES/"행정동별_관로노후도.csv")
    d["dong"] = d["행정동"].map(_norm)
    return d
