# FieldShift local backend

## ML planning integration

Send `examples/fieldshift-request.planning-ml.json` to
`POST /api/v1/planning/compare`. Setting `yield_basis` to `ml_prediction`
selects Allen County corn/soybean estimates for historical pairs 2022-2023
and 2023-2024. `examples/fieldshift-response.planning-ml.json` contains the
prepared result. The example retains 35% margin / 65% shortfall weights and
2025 price/cost proxies held constant across the 2026-2027 planning years.

`backend/data/allen-ml-yields.json` is a derived six-record county slice read
from the supplied attachments. It retains source filenames, file identities,
line numbers and the observed yields alongside each prediction. Full CSV
transfer was unavailable. This compact slice is sufficient to run this county
locally. Prediction units are inferred from matching the observed-yield fields
to the compiled bu/harvested-acre data in every included crop-year. The loader
repeats that crosscheck before calculating margins. Model version and evaluation
split remain unconfirmed. Export estimates may include training rows.

The request's yield basis defaults to observed county yields for existing
callers. ML requests require complete model predictions across the common
scenario set. Missing predictions exclude a pair with explicit reasons and an
empty common set returns 422. Each scenario joins yield and environmental
analysis by the actual historical crop/year. Planning-year labels identify
budget years. Each scenario is aggregated before score normalization.

## Planning across historical scenarios

`POST /api/v1/planning/compare` evaluates Allen County corn/soybean rotations
for two planning years. Use `examples/fieldshift-request.planning.json` and
`examples/fieldshift-response.planning.json`. Both historical pairs (2023-2024
and 2024-2025) receive equal weight. Each season uses its prepared daily water
analysis and observed county yield. Each planning year requires explicit corn
and soybean price/cost budgets. The example holds 2025 national prices and
regional costs constant for both 2026 and 2027 without inflation adjustment.
These example budgets are assumptions, not independently estimated forecasts.

The endpoint returns a scored baseline and up to two alternatives, individual
scenario results, scenario counts and min/max ranges. Average annual margins
and two-year shortfalls are calculated before score normalization. All
strategies share the same complete pairs. Pair exclusions include reasons.
The pairs overlap, so their outcomes are dependent. The ranges describe these
scenarios, not confidence intervals. The candidate library includes all four
corn/soybean sequences, subject to the family filter for alternatives.

The observed-yield mode returns `observed_county_yield`. The ML option described
above uses its own matched historical pairs. Both use the daily bucket assumptions.

Current status: demo and Allen County 2024-2025 historical comparisons work.
`GET /api/v1/capabilities` lists the prepared county/year choices for the
frontend. Simon's prediction import boundary is ready; forecast ranking is not
enabled pending his files and explicit scenario/economics/environment inputs.

Run from the repository root (PowerShell):

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

`POST /api/v1/rotations/compare` accepts `examples/fieldshift-request.example.json`.
The sample returns exactly `examples/fieldshift-response.example.json`: one scored
farmer-selected baseline, retained even when it fails the family filter, plus two
ranked alternatives. This route still uses illustrative demo values.

## First historical input slice

`GET /api/v1/counties/20001/seasons/2024/inputs` returns Allen County, Kansas,
2024 corn, soybean and sorghum inputs. Rebuild the checked-in slice with:

```powershell
.venv\Scripts\python.exe backend\county_inputs.py --data-dir ..\Data
.venv\Scripts\python.exe -m unittest backend.test_contract -v
```

The loader preserves five-digit FIPS, reads BOM-bearing CSVs, requires unique
joins, joins planting water to heat by exact date, rejects missing/nonfinite
numeric values, and uses 2024 yield, price and cost columns. No 2026 planning
budget is substituted. The compact JSON includes raw source records and relative
source filenames; the API does not scan the large CSV files on every request.

Margin is a proxy: county reported yield (bu/harvested acre) times national price
($/bu), minus regional cost ($/planted acre). This assumes equal harvested and
planted area. It is not a measured county profit or a rotation-specific estimate.
CDL shares do not determine a farmer's baseline. SMAP shallow and full-meter
water must not be added. Monthly stage ET columns describe alternative stages,
not additive water demands. Heat screens are not verified crop maturity.

## Historical integration approach

The inputs endpoint exposes one actual season. The historical comparison below
uses two prepared seasons, rather than returning demo water scores under a
historical label. The environmental preparation joins daily ET and ZIP precipitation,
apply the crop stage calendar/Kc to daily ET, initialize the soil water balance
on the planting date and begin updates the following day, and check complete
date coverage. Root access, drainage/runoff and maturity assumptions need to be
explicit. Then either load another historical season or explicitly label a
single-season weather replay across the two-year horizon. Keep the farmer's
baseline separate from alternative ranks and return missing-data reasons rather
than a fabricated passing heat status or zero shortfall.

## Environmental analysis (independent of Simon's ML)

The source directory now uses a flat layout. The input loader accepts the older
`share/` and `cost/` paths too, and uses `nasa_data_merged(simon).csv` when the
older standalone county yield file is absent. Its yields are observed historical
values, never labeled ML predictions.

```powershell
.venv\Scripts\python.exe -m backend.prepare_analysis
.venv\Scripts\python.exe -m unittest backend.test_contract backend.test_environment -v
```

`GET /api/v1/counties/20001/seasons/2024/analysis` serves the prepared analysis.
Corn, soybeans and sorghum pass the reference thermal screen in this slice.
Missing daily ET produces `water_assessment.status = unavailable`, a reason,
and a null shortfall. Monthly mean ET is never silently treated as daily data.
The dashboard comparison POST continues to reproduce its demo example exactly.

To calculate water once the previously compiled daily ET file is available:

```powershell
.venv\Scripts\python.exe -m backend.prepare_analysis --daily-et '..\Data\county_daily_reference_et_2015_2026.csv'
```

The ET CSV needs `county_fips,date,eto_mm_day`. The preparation command streams
county precipitation from the existing ZIP, validates unique daily keys and
requires complete growing-season dates. It calculates lower and upper Kc
scenarios separately, with monthly and seasonal totals. Partial records remain
unavailable with a specific reason, not a zero deficit.

### Water model assumptions

The daily bucket uses a fixed depth equal to the crop's lower mature-root-depth
reference capped at one meter. Capacity and initial top-meter SMAP water scale
to that depth under a uniform-profile assumption. This is a mature-root-zone
screening scenario, not a seedling/root-growth model. The 5cm water estimate is
not added. Updates start the day after planting-day SMAP; planting-day ET and
rain are excluded. Initial and midseason Kc stay constant; development and late
Kc interpolate to their final coefficient on the last day of each stage.

Each day: excess = max(0, storage + rain - capacity); available = min(capacity,
storage + rain); supplied = min(available, demand); shortfall = demand - supplied;
new storage = available - supplied. Irrigation is zero. All precipitation enters
the bucket, and overflow leaves before uptake. There is no explicit infiltration,
snowmelt, dynamic root growth, depletion-stress coefficient, or yield-loss model.
The calendar endpoint uses the reference stage lengths, independently of the
thermal maturity screen. These limits must accompany any calculated shortfall.

Single-season analysis feeds the two-year historical ranking described below.
No historical score is emitted unless both seasons have complete inputs.

### Verified Allen County 2024 run with restored daily ET

Daily ET and precipitation now cover all modeled updates for the three crops.
Prepared `data/allen-2024-analysis.json` reports calculated water assessments.
Under the fixed-depth, zero-irrigation assumptions above:

| Crop | Modeled demand (mm) | Rainfed shortfall (mm) | Days updated |
| --- | ---: | ---: | ---: |
| Corn | 762.21–792.05 | 304.55–324.05 | 169 |
| Soybeans | 695.95 | 292.53 | 139 |
| Sorghum | 528.31–570.62 | 162.92–205.07 | 124 |

Ranges reflect lower/upper crop coefficients, not statistical confidence intervals.
The period excludes planting day; subsequent days follow the reference stage
calendar. Monthly sums and seasonal water conservation are checked in tests.
These are modeled historical screening results, not observed crop deficits or
irrigation recommendations. The demo comparison response remains unchanged.

## Two-year historical comparison (current integration)

`POST /api/v1/rotations/compare` now accepts `data_mode: "historical"` for Allen
County (`20001`) with `first_harvest_year: 2024`. The default remains `demo`, so
the original frontend sample still matches exactly. Use
`examples/fieldshift-request.historical.json` and its matching response for the
real 2024–2025 scenario. A farmer-selected baseline is required in historical
mode. Only this county/year pair is prepared; unsupported pairs return 404.

Rebuild the second season:

```powershell
.venv\Scripts\python.exe -m backend.prepare_analysis --year 2025 --daily-et '..\Data\county_daily_reference_et_2015_2026.csv'
.venv\Scripts\python.exe -m unittest backend.test_contract backend.test_environment backend.test_historical -v
```

To submit the saved request to a running local server:

```powershell
$historicalRequest = Get-Content -Raw examples\fieldshift-request.historical.json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/rotations/compare -ContentType 'application/json' -Body $historicalRequest
```

Each rotation uses its first crop's 2024 analysis and second crop's 2025 analysis.
Annual margin is the average of the two observed-yield margin proxies. Water is
the sum of the two seasonal upper-Kc shortfalls, with lower-Kc totals also
provided. Both years independently initialize from their planting-day SMAP.
This compares historical crop/year combinations, not previous-crop effects or a
continuous multi-year soil simulation. Prices, costs and yields all use their
actual harvest year; no future-year labels are substituted.

Heat screens and complete yield/water data determine scoring eligibility.
The family checkbox filters alternatives only. A complete baseline stays scored
even if it fails that checkbox. A baseline with missing data stays in `baseline`
with null score and explicit reasons; complete alternatives still rank, with
null baseline score deltas. Other incomplete candidates appear in `unranked`.

Normalization uses all complete eligible candidates and a complete baseline
before selecting two alternatives. An indicator tie receives 0.5 for everyone;
score ties break by rotation ID. The candidate library is the existing four
sequences plus the selected supported baseline, not an exhaustive crop search.

At the example's 35% margin / 65% lower-shortfall weights:

| Role | Sequence | Annual margin proxy ($/acre/year) | Two-year upper-Kc shortfall (mm) | Score |
| --- | --- | ---: | ---: | ---: |
| Baseline | Corn → Corn | -220.77 | 446.28 | 18.63 |
| Alternative 1 | Sorghum → Soybeans | -179.97 | 327.47 | 100.00 |
| Alternative 2 | Corn → Soybeans | -222.44 | 446.46 | 17.86 |

Scores are relative, not percentages of success. Negative margins are retained.
An alternative can score below the baseline. Allen County's 2025 sorghum yield
is missing; selecting a sequence that needs it produces a missing-yield reason.
The 2025 seasonal analysis is also available through the existing analysis GET
route. Simon's ML has not been connected; `yield_basis` remains explicitly
`observed_county_yield` in every scored season.

## Simon's yield prediction handoff

`backend.predictions.load_crop_csv` imports separate corn, oats and soybean
files without requiring Simon to rename their columns. Configure the exact
FIPS and prediction columns after he confirms them. Historical `yield` is
never automatically selected. Example configuration (column names are only
illustrative; there are no real predictions bundled here):

```python
from backend.predictions import load_crop_csv, PredictionStore

records = load_crop_csv(
    'corn_predictions.csv', crop='corn', fips_column='county_fips',
    prediction_column='yield 2026', harvest_year=2026,
    scenario_id='confirmed-scenario-id', yield_unit='bu/acre',
    model_version='confirmed-model-version',
    weather_assumptions='Replace with Simon\'s actual weather assumptions',
    # Set only if the file has multiple historical feature rows per county:
    # row_filters={'year': '2024'},
)
store = PredictionStore(records)
prediction = store.get('20001', 'corn', 2026, 'confirmed-scenario-id')
```

Combine records from the three files in one `PredictionStore`. Imports reject
duplicate county/crop/year/scenario keys, missing columns, malformed rows,
invalid FIPS and negative/nonfinite predictions. Numeric FIPS are padded to
five digits; decimal FIPS are rejected. Blank yields stay `None`, while an
explicit zero stays zero. Units must be confirmed as `bu/acre` (per harvested
acre); no implicit conversion occurs. Each record retains its source file,
row, model version, weather assumptions and `yield_basis: ml_prediction`.

If the final output has many county-year rows with the forecast repeated on
each, confirm which row represents the intended scenario and configure an
explicit `row_filters` selection; never silently choose the first/last row.
For county-year historical estimates, use `year_column='year'` instead of a
fixed `harvest_year`. This preserves every year and rejects duplicate keys.
Missing lookups return `None`, without substituting observed yields or another
year's prediction. Oats import support does not imply oats ranking support:
its environmental coverage is not prepared yet.

This module does not change either comparison mode. Before enabling a planning
mode, match prediction years/scenarios with explicit price/cost assumptions
and water/heat scenarios. A single 2026 yield is not a separate 2027 forecast.
Reported model metrics should accompany the final model handoff, independently
of farmer priority weights. No extra weather-based yield penalty is applied.

Run all checks from the repository root:

```powershell
.venv\Scripts\python.exe -m unittest discover -s backend -p 'test_*.py' -v
```

### Received prediction exports (November 15)

Full-content inspection of Simon's supplied exports found identical headers:
`county_fips`, `county_name`, coordinates, `year`, crop-share delta features,
NASA weather features, observed `yield`, and `predicted_yield`.

| File | Data rows | Counties | Years |
| --- | ---: | ---: | --- |
| corn_with_predictions.csv | 7,346 | 1,873 | 2020-2024 |
| oats_with_predictions.csv | 1,178 | 500 | 2020-2024 |
| soybeans_with_predictions.csv | 6,560 | 1,654 | 2020-2024 |

No duplicate county/year keys, malformed field counts, or blank, nonfinite,
negative prediction values were found. These are historical county-year model
estimates, not 2026 forecasts. The files contain no units, train/test flags,
split-year details, or model version fields. Crop-share `*_delta` features do
not by themselves establish a chronological validation split or causal field
rotation effects. Do not recompute evaluation metrics from the entire export
and label them held-out performance.

Configure `fips_column='county_fips'`, `prediction_column='predicted_yield'`,
`year_column='year'` (omit `harvest_year`) after confirming units and model
metadata. Do not average county years or relabel 2024 as 2026. Historical weather
features should be described as the model's historical inputs, not a forecast.

Allen County has corn predictions for 2020-2024, soybeans for 2020, 2022-2024,
and oats only for 2020. Corn/soybean overlap in 2023-2024 could support a separate
model-estimate replay once 2023 environmental analysis is prepared and units
are confirmed. It cannot replace both seasons of the existing 2024-2025
comparison, since 2025 predictions are absent. The observed-yield historical
comparison is unchanged. These files do not identify which exported rows were
used in training, so the replay must not be called independent forecast
validation. The source CSVs are not bundled with the backend.
