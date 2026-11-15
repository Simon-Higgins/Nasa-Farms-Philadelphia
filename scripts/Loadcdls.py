
from pathlib import Path
import csv
import math

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import transform as window_transform
from pyproj import Transformer

# =====================================
# SETTINGS
# =====================================

BASE_DIR = Path(__file__).resolve().parent.parent

FILES = {
    2019: BASE_DIR / "2019" / "2019_30m_cdls.tif",
    2020: BASE_DIR / "2020" / "2020_30m_cdls.tif",
    2021: BASE_DIR / "2021" / "2021_30m_cdls.tif",
    2022: BASE_DIR / "2022" / "2022_30m_cdls.tif",
    2023: BASE_DIR / "2023" / "2023_30m_cdls.tif",
    2024: BASE_DIR / "2024" / "2024_30m_cdls.tif",
    2025: BASE_DIR / "2025" / "2025_30m_cdls.tif"
}

GRID_SIZE = 5000  # meters (5000 = 5 km)
GRID_CRS = "EPSG:5070"

OUTPUT = BASE_DIR / "files" / "national_crop_rotations.csv"

# USDA CDL crop codes
CROPS = {
    "corn": [1],
    "soybeans": [5],
    "spring_wheat": [23],
    "winter_wheat": [24],
    "durum_wheat": [22],
    "barley": [21],
    "oats": [28],
    "rye": [27],
    "sorghum": [4],
    "rice": [3],
    "cotton": [2],
    "potatoes": [43],
    "alfalfa": [36],
    "other_hay": [37],
    "sunflower": [6],
    "canola": [31],
    "sugarbeets": [41],
    "dry_beans": [42],
    "peanuts": [10],
    "fallow": [61],
}

# =====================================
# FIND COMMON NATIONAL GRID
# =====================================

bounds = []

for year, path in FILES.items():
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    with rasterio.open(path) as src:
        b = transform_bounds(
            src.crs,
            GRID_CRS,
            *src.bounds,
            densify_pts=21
        )
        bounds.append(b)

xmin = math.floor(min(b[0] for b in bounds) / GRID_SIZE) * GRID_SIZE
ymin = math.floor(min(b[1] for b in bounds) / GRID_SIZE) * GRID_SIZE
xmax = math.ceil(max(b[2] for b in bounds) / GRID_SIZE) * GRID_SIZE
ymax = math.ceil(max(b[3] for b in bounds) / GRID_SIZE) * GRID_SIZE

COLS = round((xmax - xmin) / GRID_SIZE)
ROWS = round((ymax - ymin) / GRID_SIZE)
N = ROWS * COLS

print(f"Grid: {ROWS:,} rows x {COLS:,} columns")
print(f"Possible cells: {N:,}")

# =====================================
# PROCESS ONE YEAR IN CHUNKS
# =====================================

def aggregate_year(year, path):

    crop_counts = {
        crop: np.zeros(N, dtype=np.int64)
        for crop in CROPS
    }

    total_counts = np.zeros(N, dtype=np.int64)

    with rasterio.open(path) as src:

        print(f"\nProcessing {year}")
        print(f"Raster CRS: {src.crs}")

        needs_transform = str(src.crs) != GRID_CRS

        if needs_transform:
            transformer = Transformer.from_crs(
                src.crs, GRID_CRS, always_xy=True
            )

        block_count = sum(
            1 for _ in src.block_windows(1)
        )

        for block_num, (_, window) in enumerate(
            src.block_windows(1), start=1
        ):

            data = src.read(1, window=window, masked=True)

            valid = ~np.ma.getmaskarray(data)
            valid &= data.data != 0

            rr, cc = np.nonzero(valid)

            if len(rr) == 0:
                continue

            # Coordinates of pixel centers
            t = window_transform(window, src.transform)

            px = cc + 0.5
            py = rr + 0.5

            x = t.c + px * t.a + py * t.b
            y = t.f + px * t.d + py * t.e

            if needs_transform:
                x, y = transformer.transform(x, y)

            grid_col = np.floor(
                (x - xmin) / GRID_SIZE
            ).astype(np.int64)

            grid_row = np.floor(
                (y - ymin) / GRID_SIZE
            ).astype(np.int64)

            inside = (
                (grid_col >= 0) &
                (grid_col < COLS) &
                (grid_row >= 0) &
                (grid_row < ROWS)
            )

            indices = (
                grid_row[inside] * COLS +
                grid_col[inside]
            )

            codes = data.data[rr, cc][inside]

            # Count all valid pixels
            np.add.at(total_counts, indices, 1)

            # Count each crop separately
            for crop, crop_codes in CROPS.items():

                mask = np.isin(codes, crop_codes)

                np.add.at(
                    crop_counts[crop],
                    indices[mask],
                    1
                )

            if block_num % 500 == 0:
                print(
                    f"{year}: {block_num:,}/{block_count:,} blocks"
                )

    return crop_counts, total_counts


# =====================================
# AGGREGATE ALL YEARS
# =====================================

results = {}

for year, path in FILES.items():
    results[year] = aggregate_year(year, path)

# =====================================
# EXPORT ONE ROW PER GRID LOCATION
# =====================================

to_gps = Transformer.from_crs(
    GRID_CRS, "EPSG:4326", always_xy=True
)

years = sorted(FILES.keys())

headers = [
    "grid_id",
    "latitude",
    "longitude",
    "grid_x",
    "grid_y",
]

for year in years:

    for crop in CROPS:
        headers.append(f"{crop}_pct_{year}")

    headers += [
        f"other_pct_{year}",
        f"pixel_count_{year}",
    ]

print("\nWriting CSV...")

with open(OUTPUT, "w", newline="", encoding="utf-8") as f:

    writer = csv.writer(f)
    writer.writerow(headers)

    exported = 0

    for index in range(N):

        # Skip locations with no data
        if all(results[y][1][index] == 0 for y in years):
            continue

        row_idx = index // COLS
        col_idx = index % COLS

        x = xmin + (col_idx + 0.5) * GRID_SIZE
        y = ymin + (row_idx + 0.5) * GRID_SIZE

        lon, lat = to_gps.transform(x, y)

        record = [
            index,
            round(lat, 6),
            round(lon, 6),
            round(x, 2),
            round(y, 2),
        ]

        for year in years:

            crop_counts, total = results[year]

            n = total[index]

            if n == 0:
                record += [""] * (len(CROPS) + 1)
                record.append(0)
                continue

            tracked = 0

            for crop in CROPS:

                count = crop_counts[crop][index]
                tracked += count

                record.append(
                    round(100 * count / n, 2)
                )

            other = n - tracked

            record += [
                round(100 * other / n, 2),
                int(n),
            ]

        writer.writerow(record)
        exported += 1

print(f"\nDONE! Exported {exported:,} grid cells.")
print(f"Saved to: {OUTPUT}")
