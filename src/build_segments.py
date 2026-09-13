"""구간 2 B단계 — 도로 구간(A안)에 경사·강우·관로·계단을 결합해 segments_base 생성."""
import geopandas as gpd, pandas as pd, numpy as np, rasterio, re, time, json
from rasterio.transform import rowcol
from scipy.ndimage import percentile_filter
from shapely.geometry import Point

A="/tmp/a1"; t0=time.time()
E  = gpd.read_parquet(f"{A}/edges_clipped.parquet")
sg = gpd.read_parquet(f"{A}/admdong.parquet")
ST = gpd.read_parquet(f"{A}/steps.parquet")
print(f"[입력] 구간 {len(E):,} | 행정동 {len(sg)} | 계단 피처 {len(ST)}")

# ── 표고 (창3·하위25%)
with rasterio.open(f"{A}/dem_5187.tif") as d:
    RAWD=d.read(1).astype('float32'); T=d.transform
RAWD=np.where(RAWD==-9999,np.nan,RAWD)
DTM=percentile_filter(np.where(np.isnan(RAWD),np.nanmax(RAWD),RAWD),25,size=3,mode='nearest')
H,W=DTM.shape
def zat(x,y):
    r,c=rowcol(T,x,y); return DTM[np.clip(np.asarray(r),0,H-1), np.clip(np.asarray(c),0,W-1)]

# ── 경사: 20 m 간격 샘플링 → 최소제곱 회귀 기울기. 20 m 미만은 결측
STEP, MINLEN = 20.0, 20.0
fit=np.full(len(E),np.nan); mx=np.full(len(E),np.nan); nsamp=np.zeros(len(E),int)
for i,(g,L) in enumerate(zip(E.geometry.values, E.len_m.values)):
    if L < MINLEN: continue
    dd=np.arange(0,L+STEP,STEP)
    if len(dd)<2: dd=np.array([0.0,L])
    P=[g.interpolate(t) for t in dd]
    z=zat(np.array([p.x for p in P]), np.array([p.y for p in P]))
    if np.all(np.isnan(z)): continue
    fit[i]=abs(np.polyfit(dd,z,1)[0]); nsamp[i]=len(dd)
    s=np.abs(np.diff(z)/np.maximum(np.diff(dd),1e-9)); mx[i]=np.nanmax(s) if len(s) else np.nan
    if i%20000==0 and i: print(f"   경사 {i:,}/{len(E):,}  {time.time()-t0:.0f}s")
E['slope_fit']=fit; E['slope_max']=mx; E['slope_n']=nsamp
print(f"[경사] 산출 {np.isfinite(fit).sum():,} | 20m미만 결측 {(E.len_m<MINLEN).sum():,} | >0.5 {int(np.nansum(fit>0.5))} | {time.time()-t0:.0f}s")

# ── 대표점: 선 위의 점(중심점은 선 밖으로 나갈 수 있음)
rep = E.geometry.interpolate(0.5, normalized=True)
E['rep_x']=rep.x.values; E['rep_y']=rep.y.values

# ── 강우 평면 추세면
co=pd.read_csv(f"{A}/aws_추세면_계수.csv"); x0,y0=co.기준x.iloc[0],co.기준y.iloc[0]
dx=(E.rep_x.values-x0)/1000; dy=(E.rep_y.values-y0)/1000
for r in co.itertuples():
    E['rain_mm' if '연강수' in r.변수 else 'rain_ge30'] = r.절편 + r.동서계수*dx + r.남북계수*dy
print(f"[강우] 연강수 {E.rain_mm.min():.0f}~{E.rain_mm.max():.0f} mm | 30mm↑ {E.rain_ge30.min():.2f}~{E.rain_ge30.max():.2f} 회/년")

# ── 행정동 귀속 (대표점 within → 실패분은 최근접)
pts=gpd.GeoDataFrame(geometry=[Point(a,b) for a,b in zip(E.rep_x,E.rep_y)], crs=5187)
j=gpd.sjoin(pts, sg[['gu','dong','adm_cd','geometry']], how='left', predicate='within')
j=j[~j.index.duplicated()]
miss=j.dong.isna().values
print(f"[행정동] within 실패 {miss.sum():,}건 → 최근접으로 보정")
if miss.sum():
    nn=gpd.sjoin_nearest(pts[miss], sg[['gu','dong','adm_cd','geometry']], how='left')
    nn=nn[~nn.index.duplicated()]
    for c in ['gu','dong','adm_cd']: j.loc[miss,c]=nn[c].values
E['gu']=j.gu.values; E['dong']=j.dong.values; E['adm_cd']=j.adm_cd.values

# ── 관로 (행정동 속성 조인)
pa=pd.read_csv("/tmp/a1/_t/outputs/tables/행정동별_관로노후도.csv")
pa['dong']=pa['행정동'].map(lambda s: re.sub(r'제(\d)',r'\1',str(s)))
pa=pa[['gu' if 'gu' in pa.columns else '구군','dong','맨홀수','평균매설연수','노후30비율','신뢰도']]
pa.columns=['gu','dong','pipe_n','pipe_age_mean','pipe_old30_pct','pipe_conf']
E=E.merge(pa, on=['gu','dong'], how='left')
print(f"[관로] 결합 실패 {E.pipe_age_mean.isna().sum():,}건 | 서로 다른 매설연수 값 {E.pipe_age_mean.nunique()}개")

# ── 계단: 부산 경계로 클리핑한 피처의 3 m 버퍼와 겹치는 길이
#    10 m 버퍼는 인접 도로까지 잡아 2,022개로 부풀었다(기준선 598/585). 3 m가 맞다.
ST = ST[ST.intersects(sg.union_all())].reset_index(drop=True)
buf = ST.buffer(3).union_all()
hit = E.geometry.intersects(buf)
E['steps_len_m'] = 0.0
E.loc[hit,'steps_len_m'] = E.loc[hit,'geometry'].intersection(buf).length
E['steps_frac'] = (E.steps_len_m/E.len_m).clip(0,1)
E['steps_frac'] = E.steps_frac.fillna(0)
E['has_steps']  = E.steps_frac >= 0.5
E['steps_tag']  = E['highway'].astype(str).str.contains('steps')
print(f"[계단] 피처 {len(ST)}개 · has_steps {int(E.has_steps.sum())} · steps_tag {int(E.steps_tag.sum())}")

# ── 고립 서브그래프 제거 (WBS 2단계). 클리핑으로 본토에서 떨어져 나온 것들.
import networkx as nx
g = nx.Graph(); g.add_edges_from(zip(E.u, E.v))
comps = sorted(nx.connected_components(g), key=len, reverse=True)
if len(comps) > 1:
    iso = set().union(*comps[1:])
    drop = E.u.isin(iso) | E.v.isin(iso)
    print(f"[고립] 서브그래프 {len(comps)-1}개 · 구간 {int(drop.sum())}개 ({E.loc[drop,'len_m'].sum()/1000:.1f} km) 제거")
    E = E[~drop].reset_index(drop=True)

# ── 저장
cols=['seg_id','highway','name','oneway','bridge','tunnel','len_m',
      'slope_fit','slope_max','slope_n','rain_mm','rain_ge30',
      'gu','dong','adm_cd','pipe_n','pipe_age_mean','pipe_old30_pct','pipe_conf',
      'has_steps','steps_tag','steps_len_m','steps_frac','geometry']
G=gpd.GeoDataFrame(E[cols], geometry='geometry', crs=5187)
for c in ['highway','name','oneway','bridge','tunnel']: G[c]=G[c].astype(str)
G.to_parquet("/tmp/b1/segments_base.parquet")
G.to_file("/tmp/b1/segments_base.gpkg", layer="segments", driver="GPKG")
G.drop(columns='geometry').to_parquet("/tmp/b1/segments_attrs.parquet")
print(f"\n[저장] segments_base.gpkg  {len(G):,}행 × {len(cols)}컬럼  {time.time()-t0:.0f}s")
