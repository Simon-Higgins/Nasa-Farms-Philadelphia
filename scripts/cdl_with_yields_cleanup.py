
from pathlib import Path
import re

import numpy as np
import pandas as pd

# =====================================
# 1. FILE PATHS
# =====================================

BASE = Path(__file__).resolve().parent.parent
FILES = BASE / "files"

INPUT = FILES / "cdl_with_yields.csv"
OUTPUT = FILES / "cdl_with_yields_aggregated_cleaned.csv"

if not INPUT.exists():
    raise FileNotFoundError(f"Input file not found: {INPUT}")

# =====================================
# 2. LOAD DATA
# =====================================

print("Loading CDL and yield data...")

df = pd.read_csv(
    INPUT,
    dtype={"county_fips": "string"},
    low_memory=False
)

df.columns = df.columns.str.strip()

if "county_fips" not in df.columns:
    raise ValueError("Missing county_fips column")

# Clean county FIPS
df["county_fips"] = (
    df["county_fips"]
    .str.strip()
    .str.replace(r"\.0$", "", regex=True)
    .str.zfill(5)
)

# Remove rows without county FIPS
df = df.dropna(subset=["county_fips"]).copy()

# Remove malformed FIPS values
df = df[
    df["county_fips"].str.fullmatch(r"\d{5}", na=False)
].copy()

print(f"Loaded {len(df):,} grid cells")
print(f"Unique counties: {df['county_fips'].nunique():,}")

# =====================================
# 3. IDENTIFY CROP AND PIXEL COLUMNS
# =====================================

# Examples:
# corn_pct_2024
# soybeans_pct_2025

crop_columns = [
    col for col in df.columns
    if re.fullmatch(r".+_pct_\d{4}", col)
]

# Examples:
# pixel_count_2024
# pixel_count_2025

pixel_columns = [
    col for col in df.columns
    if re.fullmatch(r"pixel_count_\d{4}", col)
]

if not crop_columns:
    raise ValueError("No crop percentage columns found")

if not pixel_columns:
    raise ValueError("No pixel count columns found")

years = sorted(
    int(col.rsplit("_", 1)[-1])
    for col in pixel_columns
)

print(f"Years found: {years}")
print(f"Crop percentage columns: {len(crop_columns)}")

# =====================================
# 4. IDENTIFY COUNTY-LEVEL YIELD COLUMNS
# =====================================

# These are geographic columns that should
# not be retained after aggregation.

geographic_columns = {
    "grid_id",
    "latitude",
    "longitude",
    "grid_x",
    "grid_y",
    "county_fips",
}

# Everything else is assumed to be
# county-level information, such as yields.

exclude = (
    geographic_columns
    | set(crop_columns)
    | set(pixel_columns)
)

county_columns = [
    col for col in df.columns
    if col not in exclude
]

print(f"County-level columns: {len(county_columns)}")

# =====================================
# 5. INITIALIZE COUNTY RESULTS
# =====================================

print("\nAggregating by county FIPS...")

grouped = df.groupby(
    "county_fips",
    sort=True
)

result = pd.DataFrame(
    index=sorted(df["county_fips"].unique())
)

result.index.name = "county_fips"

# =====================================
# 6. WEIGHTED CROP AGGREGATION
# =====================================

for year in years:

    print(f"Processing crop percentages for {year}...")

    pixel_col = f"pixel_count_{year}"

    # Convert pixel counts to numeric values.
    weights = pd.to_numeric(
        df[pixel_col],
        errors="coerce"
    ).fillna(0)

    # Ensure invalid negative counts do not
    # contribute to the aggregation.
    weights = weights.clip(lower=0)

    # Total valid pixels per county for this year
    county_pixels = weights.groupby(
        df["county_fips"]
    ).sum()

    result[pixel_col] = county_pixels.reindex(
        result.index,
        fill_value=0
    )

    # Identify crop columns for this year
    year_crop_columns = [
        col for col in crop_columns
        if col.endswith(f"_{year}")
    ]

    for crop_col in year_crop_columns:

        percentages = pd.to_numeric(
            df[crop_col],
            errors="coerce"
        )

        # Only use observations with valid
        # percentages and positive pixel counts.
        valid = (
            percentages.notna()
            & np.isfinite(percentages)
            & (weights > 0)
        )

        # Weighted percentage contributions
        weighted_values = (
            percentages[valid] * weights[valid]
        )

        # Sum weighted values for each county
        weighted_sum = weighted_values.groupby(
            df.loc[valid, "county_fips"]
        ).sum()

        # Sum weights with valid observations
        valid_weight_sum = weights[valid].groupby(
            df.loc[valid, "county_fips"]
        ).sum()

        # Weighted average crop percentage
        county_percentage = (
            weighted_sum / valid_weight_sum
        )

        result[crop_col] = county_percentage.reindex(
            result.index
        )

# =====================================
# 7. PRESERVE USDA COUNTY YIELDS
# =====================================

print("\nPreserving USDA county-level yields...")

for col in county_columns:

    # Every grid cell assigned to the same
    # county should have the same yield value.
    unique_counts = grouped[col].nunique(
        dropna=True
    )

    inconsistent = unique_counts[
        unique_counts > 1
    ]

    if not inconsistent.empty:

        examples = inconsistent.index.tolist()[:10]

        raise ValueError(
            f"Conflicting county values in '{col}'. "
            f"Affected counties include: {examples}. "
            "Cannot safely preserve one value."
        )

    # Keep the existing county yield unchanged
    result[col] = grouped[col].first().reindex(
        result.index
    )

# =====================================
# 8. CLEAN COLUMN ORDER
# =====================================

result = result.reset_index()

ordered_columns = ["county_fips"]

for year in years:

    ordered_columns.extend([
        col for col in crop_columns
        if col.endswith(f"_{year}")
    ])

    ordered_columns.append(
        f"pixel_count_{year}"
    )

# Add yield columns at the end
ordered_columns.extend(county_columns)

result = result[ordered_columns]

# =====================================
# 9. REMOVE COUNTIES WITH NO CROPS
# =====================================

print("\nRemoving counties with no planted crops...")

# Don't count other land cover or fallow land
# as planted crops.

planted_crop_columns = [
    col for col in crop_columns
    if not col.startswith(
        ("other_pct_", "fallow_pct_")
    )
]

if not planted_crop_columns:
    raise ValueError(
        "No planted crop columns available"
    )

# Calculate total planted crop percentage
# across all available years.
#
# Do this BEFORE rounding percentages.

total_crop_pct = (
    result[planted_crop_columns]
    .fillna(0)
    .sum(axis=1)
)

before = len(result)

# Keep a county if it has ANY tracked
# planted crops in at least one year.
result = result.loc[
    total_crop_pct > 0
].copy()

removed = before - len(result)

print(f"Counties removed: {removed:,}")
print(f"Counties remaining: {len(result):,}")

# =====================================
# 10. ROUND PERCENTAGES
# =====================================

# Only round after filtering to prevent
# small crop percentages from becoming zero
# before the crop-presence test.

for col in crop_columns:
    result[col] = result[col].round(2)

# Convert integer pixel counts to nullable integers
for col in pixel_columns:
    result[col] = pd.to_numeric(
        result[col],
        errors="coerce"
    ).astype("Int64")

# =====================================
# 11. VERIFY OUTPUT
# =====================================

if result["county_fips"].duplicated().any():
    raise ValueError(
        "Duplicate county FIPS codes remain"
    )

print("\nFinal dataset summary:")
print(f"Counties: {len(result):,}")
print(f"Columns: {len(result.columns):,}")
print(f"Crop columns: {len(crop_columns)}")
print(f"Yield/other columns: {len(county_columns)}")

# =====================================
# 12. EXPORT CSV
# =====================================

result = result.sort_values(
    "county_fips"
).reset_index(drop=True)

result.to_csv(
    OUTPUT,
    index=False
)

print("\nSUCCESS!")
print(f"Saved to: {OUTPUT}")
print(f"Original grid cells: {len(df):,}")
print(f"Final counties: {len(result):,}")
