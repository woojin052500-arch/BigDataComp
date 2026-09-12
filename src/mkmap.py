import geopandas as gpd, numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
plt.rcParams['font.family']='Noto Sans CJK JP'; plt.rcParams['axes.unicode_minus']=False
BLUE=['#9ec5f4','#86b6ef','#6da7ec','#5598e7','#3987e5','#2a78d6','#256abf','#1c5cab','#184f95','#104281','#0d366b']
SEQ=LinearSegmentedColormap.from_list('seq', BLUE)
SURF='#fcfcfb'; INK='#0b0b0b'; MUTED='#898781'; HAIR='#e1e0d9'; ORANGE='#eb6834'
G=gpd.read_file('segments_base.gpkg', layer='segments'); sg=gpd.read_parquet('/tmp/a1/admdong.parquet')

def panel(ax, title, sub):
    sg.boundary.plot(ax=ax, color=HAIR, linewidth=0.25, zorder=1)
    ax.set_title(title, fontsize=11.5, color=INK, pad=22, loc='left', fontweight='bold')
    ax.text(0, 1.006, sub, transform=ax.transAxes, fontsize=8, color=MUTED, va='bottom')
    ax.set_axis_off(); ax.set_aspect('equal'); ax.set_facecolor(SURF)

def seqmap(ax, col, title, sub, unit):
    d = G.dropna(subset=[col])
    br = np.unique(np.round(d[col].quantile([0,.2,.4,.6,.8,.95,1.0]).values, 3))
    norm = BoundaryNorm(br, SEQ.N)
    panel(ax, title, sub)
    d.plot(ax=ax, column=col, cmap=SEQ, norm=norm, linewidth=0.19, zorder=2)
    cb = plt.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=SEQ), ax=ax, shrink=0.42, pad=0.01, aspect=16)
    cb.set_label(unit, fontsize=7.5, color=MUTED); cb.ax.tick_params(labelsize=6.5, colors=MUTED, length=0)
    cb.outline.set_visible(False)

fig, axes = plt.subplots(2, 2, figsize=(15, 15.5), facecolor=SURF)
fig.suptitle('구간 2 산출물 검증 — segments_base.gpkg  ·  도로 구간 83,839개  ·  EPSG:5187',
             fontsize=13.5, color=INK, y=0.962, fontweight='bold')
seqmap(axes[0,0], 'slope_fit', '① 구간 경사', '20m 간격 표고 회귀 기울기 · 20m 미만 16,137개는 결측(미표시)', 'rise/run')
seqmap(axes[0,1], 'pipe_age_mean', '② 관로 평균 매설연수', '소속 행정동 속성 조인 · 서로 다른 값 206개 상한', '년')
seqmap(axes[1,0], 'rain_mm', '③ 연평균 강수', 'AWS 13지점 평면 추세면 · LOO R² 0.169', 'mm')

ax = axes[1,1]
panel(ax, '④ 계단 구간', 'OSM 피처 598개 · 3m 버퍼에 길이 50%↑ 겹침')
G[~G.has_steps].plot(ax=ax, color='#d5d4cd', linewidth=0.14, zorder=2)
G[G.has_steps].plot(ax=ax, color=ORANGE, linewidth=1.8, zorder=3)
ax.plot([], [], color=ORANGE, lw=2, label='계단 구간 544')
ax.plot([], [], color='#d5d4cd', lw=2, label='그 외 83,295')
ax.legend(loc='lower left', fontsize=8, frameon=False, labelcolor=MUTED)

plt.tight_layout(rect=[0,0,1,0.952])
plt.savefig('구간2_검증지도.png', dpi=125, facecolor=SURF, bbox_inches='tight')
print("저장 완료")
