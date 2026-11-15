
import pandas as pd
import re
from pathlib import Path

# =====================================
# FILE PATHS
# =====================================

BASE = Path(__file__).resolve().parent.parent

FILES = BASE / "files"
OUTPUT = BASE / "training_files"

INPUT = FILES / "nasa_data_merged.csv"
# =====================================
# LOAD DATA
# =====================================

df = pd.read_csv(INPUT, dtype={"county_fips": "string"})

df["county_fips"] = df["county_fips"].str.zfill(5)

# =====================================
# DEFINE CROPS WITH YIELD DATA
# =====================================

yield_columns = {
    "corn": "corn_grain",
    "soybeans": "soybeans",
    "barley": "barley",
    "oats": "oats",
    "rice": "rice",
    "peanuts": "peanuts",
    "sorghum": "sorghum_grain",
    "dry_beans": "beans_dry_edible_excl_chickpeas"
}

# =====================================
# IDENTIFY ALL CROP PERCENTAGE COLUMNS
# =====================================

crop_types = sorted({
    re.sub(r"_pct_\d{4}$", "", col)
    for col in df.columns
    if re.fullmatch(r".+_pct_\d{4}", col)
})

# =====================================
# IDENTIFY ALL NASA FEATURES
# =====================================

nasa_features = sorted({
    re.sub(r"\s*\(\d{4}\)$", "", col).strip()
    for col in df.columns
    if re.search(r"\(\d{4}\)$", col)
})

# =====================================
# BUILD ONE DATAFRAME PER CROP
# =====================================

crop_dfs = {}

for crop, yield_name in yield_columns.items():

    rows = []

    for _, county in df.iterrows():

        for year in range(2020, 2025):

            row = {
                "county_fips": county["county_fips"],
                "county_name": county["county_name"],
                "lat": county["lat"],
                "lon": county["lon"],
                "year": year
            }

            # Calculate all crop percentage deltas
            for crop_type in crop_types:

                current = county.get(
                    f"{crop_type}_pct_{year}"
                )

                previous = county.get(
                    f"{crop_type}_pct_{year - 1}"
                )

                if pd.notna(current) and pd.notna(previous):
                    row[f"{crop_type}_delta"] = current - previous
                else:
                    row[f"{crop_type}_delta"] = None

            # Add NASA weather features for this year
            for feature in nasa_features:

                column = f"{feature} ({year})"

                row[feature] = county.get(column)

            # Find the yield column for this crop and year
            yield_col = next(
                (
                    col for col in df.columns
                    if col.startswith(
                        f"{yield_name}_yield_measured_in_"
                    )
                    and col.endswith(f"_{year}")
                ),
                None
            )

            if yield_col is not None:
                row["yield"] = county[yield_col]
            else:
                row["yield"] = None

            rows.append(row)

    # Convert rows to a DataFrame
    crop_df = pd.DataFrame(rows)

    # Remove rows without a yield measurement
    crop_df = crop_df.dropna(subset=["yield"])

    # Store dataframe in dictionary
    crop_dfs[crop] = crop_df

    # Save crop dataset
    crop_df.to_csv(
    OUTPUT / f"{crop}_training.csv",
    index=False
)
    print(f"{crop}: {crop_df.shape}")

# =====================================
# ACCESS INDIVIDUAL DATAFRAMES
# =====================================

corn_df = crop_dfs["corn"]
soybeans_df = crop_dfs["soybeans"]
barley_df = crop_dfs["barley"]
oats_df = crop_dfs["oats"]
rice_df = crop_dfs["rice"]
peanuts_df = crop_dfs["peanuts"]
sorghum_df = crop_dfs["sorghum"]
dry_beans_df = crop_dfs["dry_beans"]

print(corn_df.head())
