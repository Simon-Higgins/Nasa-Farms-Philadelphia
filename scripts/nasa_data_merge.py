import pandas as pd
from pathlib import Path



BASE = Path(__file__).resolve().parent.parent
FILES = BASE / "files"

crop_yields_and_rotations = pd.read_csv(FILES / "cdl_with_yields_aggregated_cleaned.csv")
nasa_data = pd.read_csv(FILES / "NASA_POWER.csv")

full_dataset = crop_yields_and_rotations.merge(nasa_data,left_on="county_fips",right_on="fips_code",how="left")

OUTPUT = BASE / "files" / "nasa_data_merged.csv"

full_dataset.to_csv(OUTPUT, index=False)

