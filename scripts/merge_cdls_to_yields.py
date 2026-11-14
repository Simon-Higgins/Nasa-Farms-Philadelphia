
import geopandas as gpd
import pandas as pd
from pathlib import Path

# =====================================
# 1. FILE PATHS
# =====================================

BASE = Path(__file__).resolve().parent.parent
FILES = BASE / "files"

CDL_FILE = FILES / "national_crop_rotations.csv"
YIELDS_FILE = FILES / "county_yields_wide.csv"
OUTPUT = FILES / "cdl_with_yields.csv"

# =====================================
# 2. LOAD CROPLAND DATA
# =====================================

print("Loading Cropland Data Layer...")

df = pd.read_csv(CDL_FILE, low_memory=False)

print(f"Loaded {len(df):,} grid cells")

# =====================================
# 3. CONVERT LAT/LONG TO GEOGRAPHIC POINTS
# =====================================

points = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(
        df["longitude"],
        df["latitude"]
    ),
    crs="EPSG:4326"
)

# =====================================
# 4. LOAD US COUNTY BOUNDARIES
# =====================================

print("Loading US county boundaries...")

counties = gpd.read_file(
    "https://www2.census.gov/geo/tiger/"
    "TIGER2025/COUNTY/tl_2025_us_county.zip"
)

counties = counties.to_crs(points.crs)

# =====================================
# 5. ASSIGN COUNTY FIPS TO EACH GRID CELL
# =====================================

print("Matching coordinates to counties...")

result = gpd.sjoin(
    points,
    counties[["GEOID", "geometry"]],
    how="left",
    predicate="within"
)

result = result.rename(
    columns={"GEOID": "county_fips"}
)

# Remove geographic join columns
cdl = result.drop(
    columns=["geometry", "index_right"],
    errors="ignore"
)

# Preserve 5-digit county FIPS codes
cdl["county_fips"] = (
    cdl["county_fips"]
    .astype("string")
    .str.zfill(5)
)

matched = cdl["county_fips"].notna().sum()

print(f"Matched county FIPS: {matched:,}")
print(f"Unmatched grid cells: {len(cdl) - matched:,}")

# =====================================
# 6. LOAD USDA YIELDS
# =====================================

print("Loading USDA crop yields...")

yields = pd.read_csv(
    YIELDS_FILE,
    dtype={"county_fips": "string"},
    low_memory=False
)

yields["county_fips"] = (
    yields["county_fips"]
    .str.strip()
    .str.zfill(5)
)

print(f"Loaded yields for {len(yields):,} counties")

# =====================================
# 7. MERGE CDL + USDA YIELDS
# =====================================

print("Merging datasets...")

full_dataset = pd.merge(
    cdl,
    yields,
    on="county_fips",
    how="left",
    validate="many_to_one"
)

# =====================================
# 8. VERIFY MERGE
# =====================================

yield_columns = [
    col for col in yields.columns
    if col != "county_fips"
]

has_yield = full_dataset[yield_columns].notna().any(axis=1)

print("\nMerge results:")
print(f"Total rows: {len(full_dataset):,}")
print(f"Total columns: {len(full_dataset.columns):,}")
print(f"Rows with yield data: {has_yield.sum():,}")
print(f"Rows without yield data: {(~has_yield).sum():,}")

# =====================================
# 9. EXPORT CSV
# =====================================

full_dataset.to_csv(OUTPUT, index=False)

print("\nSUCCESS!")
print(f"Saved to: {OUTPUT}")
