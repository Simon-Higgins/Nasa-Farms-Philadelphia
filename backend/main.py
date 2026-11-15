"""Local FieldShift demo. Inputs are illustrative per-rotation summaries."""

from math import isclose
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


Weight = Annotated[float, Field(ge=0, le=1)]


class Weights(StrictModel):
    margin: Weight
    lower_rainfed_shortfall: Weight

    @model_validator(mode="after")
    def check_sum(self):
        if not isclose(self.margin + self.lower_rainfed_shortfall, 1, abs_tol=1e-9):
            raise ValueError("Weights must sum to one.")
        return self


class CompareRequest(StrictModel):
    data_mode: Literal["demo", "historical"] = "demo"
    county_fips: Annotated[str, Field(pattern=r"^[0-9]{5}$")]
    first_harvest_year: int
    horizon_years: Literal[2]
    weights: Weights
    require_crop_family_change: bool
    baseline_rotation: Annotated[list[str], Field(min_length=2, max_length=2)] | None = None


app = FastAPI(title="FieldShift rotation comparison")

class CropBudget(StrictModel):
    price_usd_per_bu: float = Field(ge=0)
    cost_usd_per_acre: float = Field(ge=0)


class PlanningRequest(StrictModel):
    yield_basis: Literal['observed_county_yield', 'ml_prediction'] = 'observed_county_yield'
    county_fips: str = Field(pattern=r'^[0-9]{5}$')
    first_harvest_year: int = Field(ge=2026, le=2100)
    horizon_years: Literal[2] = 2
    baseline_rotation: list[str] = Field(min_length=2, max_length=2)
    require_crop_family_change: bool
    weights: Weights
    budgets_by_year: dict[str, dict[str, CropBudget]] | None = None
    economics_assumptions: str | None = Field(default=None, min_length=1)


@app.post('/api/v1/planning/compare')
def planning_compare(request: PlanningRequest):
    from backend.planning import compare_planning
    return compare_planning(request)


@app.get("/api/v1/capabilities")
def capabilities():
    """Prepared comparison choices; model crop coverage is not ranking coverage."""
    from backend.coverage import planning_counties
    counties = planning_counties()
    return {
        "horizon_years": 2,
        "scenarios": [
            {"data_mode": "demo", "county_fips": "01001",
             "county_label": "Autauga County, AL", "first_harvest_year": 2026,
             "crops": ["corn", "soybeans", "sorghum"],
             "yield_basis": "illustrative_demo"},
            {"data_mode": "historical", "county_fips": "20001",
             "county_label": "Allen County, KS", "first_harvest_year": 2024,
             "crops": ["corn", "soybeans", "sorghum"],
             "yield_basis": "observed_county_yield",
             "limitations": ["Sorghum yield unavailable for 2025; affected rotations cannot be scored."]},
        ],
        "ml_predictions": {"status": "prepared_county_slice", "ranking_enabled": True,
                           "county_fips": "20001", "crops": ["corn", "soybeans"],
                           "counties": counties,
                           "historical_pairs": [[2022, 2023], [2023, 2024]]},
        "planning": {
            "endpoint": "/api/v1/planning/compare", "county_fips": "20001",
            "supported_ml_counties": counties,
            "crops": ["corn", "soybeans"], "historical_pairs": [[2023, 2024], [2024, 2025]],
            "yield_basis": "observed_county_yield", "requires_explicit_budgets": False,
            "observed_requires_explicit_budgets": True,
            "ml_default_budget": {"available": True, "price_year": 2025, "cost_year": 2026,
                                  "requires_explicit_budgets": False},
        },
        "notes": ["Crop choices do not guarantee complete data for every sequence.",
                  "Historical scenarios are not forecasts."],
    }

# Assumed current plan for the demo; county crop shares cannot identify a field rotation.
DEMO_BASELINE = ("corn", "soybeans")
DEMO_CANDIDATES = [
    (("soybeans", "corn"), 150, 40),
    (("corn", "soybeans"), 180, 60),
    (("sorghum", "soybeans"), 165, 50),
    (("corn", "corn"), 145, 70),
]
FAMILIES = {"soybeans": "legume", "corn": "grass", "sorghum": "grass"}


def normalized(value, low, high):
    return (value - low) / (high - low) if high != low else 0.5


def explain(row, alternative):
    water = row["rainfed_shortfall_mm"] - alternative["rainfed_shortfall_mm"]
    margin = row["annual_margin_usd_per_acre"] - alternative["annual_margin_usd_per_acre"]
    water_text = f"{abs(water):g} mm {'more' if water > 0 else 'less'} rainfed shortfall over two years"
    margin_text = f"${abs(margin):g} {'more' if margin > 0 else 'less'} margin per acre per year"
    if water == 0:
        water_text = "equal rainfed shortfall over two years"
    if margin == 0:
        margin_text = "equal annual margin per acre"
    first, second = (margin_text, water_text) if margin > 0 else (water_text, margin_text)
    return first[:1].upper() + first[1:] + ", with " + second + "."


@app.post("/api/v1/rotations/compare")
def compare(request: CompareRequest):
    if request.data_mode == "historical":
        from backend.historical import compare_historical
        return compare_historical(request)
    if (request.county_fips, request.first_harvest_year) != ("01001", 2026):
        raise HTTPException(404, "Demo data covers county 01001 and first harvest year 2026.")

    baseline_crops = tuple(request.baseline_rotation or DEMO_BASELINE)
    benchmark = next((entry for entry in DEMO_CANDIDATES if entry[0] == baseline_crops), None)
    if benchmark is None:
        raise HTTPException(422, "Baseline rotation has no demo estimates for this crop sequence.")
    baseline = {"annual_margin_usd_per_acre": benchmark[1], "rainfed_shortfall_mm": benchmark[2]}
    candidates = [
        candidate for candidate in DEMO_CANDIDATES
        if candidate == benchmark or not request.require_crop_family_change
        or FAMILIES[candidate[0][0]] != FAMILIES[candidate[0][1]]
    ]
    margins = [margin for _, margin, _ in candidates]
    shortfalls = [water for _, _, water in candidates]
    rows = []
    for crops, margin, water in candidates:
        m = normalized(margin, min(margins), max(margins))
        w = 1 - normalized(water, min(shortfalls), max(shortfalls))
        score = 100 * (request.weights.margin * m + request.weights.lower_rainfed_shortfall * w)
        rows.append({
            "id": "-".join(crops),
            "is_baseline": crops == baseline_crops,
            "seasons": [{"harvest_year": request.first_harvest_year + i, "crop": crop}
                        for i, crop in enumerate(crops)],
            "annual_margin_usd_per_acre": margin, "rainfed_shortfall_mm": water,
            "heat_status": "passed", "margin_normalized": m, "lower_shortfall_normalized": w,
            "score": round(score, 10),
        })
    rows.sort(key=lambda row: (-row["score"], row["id"]))
    baseline_note = ("Your current rotation." if request.baseline_rotation
                     else "Assumed current rotation for this demo.")
    current = next(row for row in rows if row["is_baseline"])
    current["explanation"] = baseline_note
    current["score_delta_vs_baseline"] = 0
    current["meets_crop_family_filter"] = (
        not request.require_crop_family_change
        or FAMILIES[baseline_crops[0]] != FAMILIES[baseline_crops[1]]
    )
    alternatives = [row for row in rows if not row["is_baseline"]][:2]
    for rank, row in enumerate(alternatives, 1):
        row["rank"] = rank
        row["explanation"] = "Compared with the baseline: " + explain(row, baseline)
        row["score_delta_vs_baseline"] = round(row["score"] - current["score"], 10)

    return {
        "data_mode": "demo", "county_fips": request.county_fips,
        "county_label": "Autauga County, AL",
        "scenario_label": "Illustrative historical-weather scenario", "sources": [],
        "baseline": current, "rotations": alternatives, "unranked": [], "applied_weights": request.weights.model_dump(),
        "applied_filters": {"require_crop_family_change": request.require_crop_family_change},
    }

@app.get("/api/v1/counties/{county_fips}/seasons/{harvest_year}/inputs")
def county_season_inputs(county_fips: str, harvest_year: int):
    """First historical slice; deliberately does not fabricate rotation scores."""
    import json
    from pathlib import Path

    if (county_fips, harvest_year) != ("20001", 2024):
        raise HTTPException(404, "Historical inputs currently cover Allen County, KS (20001), 2024.")
    path = Path(__file__).resolve().parent / "data" / "allen-2024.json"
    if not path.exists():
        raise HTTPException(503, "Build historical inputs with python backend/county_inputs.py.")
    return json.loads(path.read_text(encoding="utf-8"))

@app.get("/api/v1/counties/{county_fips}/seasons/{harvest_year}/analysis")
def county_season_analysis(county_fips: str, harvest_year: int):
    import json
    from pathlib import Path

    from backend.coverage import planning_counties
    data_dir = Path(__file__).resolve().parent / 'data'
    prepared = any(c['county_fips'] == county_fips for c in planning_counties())
    if county_fips == '20001' and harvest_year in (2022, 2023, 2024, 2025):
        path = data_dir / f'allen-{harvest_year}-analysis.json'
    elif prepared and harvest_year in (2020, 2021, 2022, 2023, 2024):
        path = data_dir / 'counties' / county_fips / f'{harvest_year}-analysis.json'
    else:
        raise HTTPException(404, 'County season analysis is not prepared.')
    if not path.exists():
        raise HTTPException(503, "Run python -m backend.prepare_analysis first.")
    result = json.loads(path.read_text(encoding="utf-8"))
    if result['county_fips'] != county_fips or result['harvest_year'] != harvest_year:
        raise HTTPException(503, 'County analysis identity mismatch.')
    return result
