"""segments_base.parquet → segments_base.gpkg (QGIS 열람용)."""
import geopandas as gpd
from pathlib import Path
P = Path(__file__).resolve().parents[1] / "data" / "processed"
g = gpd.read_parquet(P / "segments_base.parquet")
g.to_file(P / "segments_base.gpkg", layer="segments", driver="GPKG")
print(f"{len(g):,}행 → {P/'segments_base.gpkg'}")
