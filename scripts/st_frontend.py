import streamlit as st
import pandas as pd
import numpy as np
import requests

st.set_page_config(page_title="FieldShift - Compare Crop Rotations", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-family: 'Arial', sans-serif !important;
        color: #1A2421;
    }
    [data-testid="stAppViewContainer"] {
        background-color: #F8F6F0;
    }
    [data-testid="stHeader"] {
        background-color: #F8F6F0;
    }
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
    }
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        border: 1px solid #C8C4B8 !important;
        border-radius: 6px !important;
        color: #1A2421 !important;
    }
    .stButton > button {
        background-color: #1A2421 !important;
        color: #F8F6F0 !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 0.55rem 1rem !important;
        font-weight: 600 !important;
        width: 100%;
    }
    .stButton > button:hover {
        background-color: #2B3B36 !important;
        color: #FDF0AC !important;
    }
    .baseline-card {
        background-color: #EAE6D9;
        border: 1px solid #D5D0C0;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 18px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .score-pill {
        background-color: #1A2421;
        color: #FDF0AC;
        font-weight: 700;
        padding: 6px 14px;
        border-radius: 6px;
        font-size: 15px;
    }
    .alt-row {
        background-color: #FFFFFF;
        border: 1px solid #DCD8CA;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    .alt-row-active {
        background-color: #FDF0AC;
        border: 1.5px solid #1A2421;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    .crop-stage-card {
        background-color: #1A2421;
        color: #F8F6F0;
        border-radius: 10px;
        padding: 20px;
        border-bottom: 4px solid #FDF0AC;
    }
    .family-tag {
        display: inline-block;
        background-color: #FDF0AC;
        color: #1A2421;
        font-size: 11px;
        font-weight: 700;
        padding: 3px 9px;
        border-radius: 4px;
        margin-top: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .summary-banner {
        background-color: #EAE6D9;
        border-left: 4px solid #1A2421;
        padding: 12px 16px;
        border-radius: 6px;
        margin-top: 16px;
        font-size: 14px;
    }
    </style>
""", unsafe_allow_html=True)

CROP_FAMILIES = {
    "Corn": "Grass / Cereal",
    "Soybeans": "Legume",
    "Spring wheat": "Grass / Cereal",
    "Winter wheat": "Grass / Cereal",
    "Durum wheat": "Grass / Cereal",
    "Barley": "Grass / Cereal",
    "Oats": "Grass / Cereal",
    "Rye": "Grass / Cereal",
    "Grain sorghum": "Grass / Cereal",
    "Rice": "Grass / Cereal",
    "Cotton": "Mallow / Fiber",
    "Potatoes": "Nightshade / Tuber",
    "Alfalfa": "Legume",
    "Sunflower": "Aster / Oilseed",
    "Canola": "Brassica / Oilseed",
    "Sugarbeets": "Amaranth / Root",
    "Dry beans": "Legume",
    "Peanuts": "Legume",
}

CROPS = list(CROP_FAMILIES.keys())
ALL_ROTATIONS = [f"{c1} -> {c2}" for c1 in CROPS for c2 in CROPS]

@st.cache_data
def get_us_counties_with_fips():
    try:
        counties_url = (
        "https:"
        "//://githubusercontent.com"
        "state_and_county_fips_master.csv"
      )

        )

        df = pd.read_csv(counties_url, dtype={"fips": str})
        df = df.dropna(subset=["state", "fips"])
        df["fips"] = df["fips"].str.strip().str.zfill(5)
        df["county_label"] = df["name"] + ", " + df["state"]
        return dict(zip(df["county_label"], df["fips"]))
    except Exception:
        return {
            "Allen County, KS": "20001",
            "Autauga County, AL": "01001",
            "Baldwin County, AL": "01003",
            "Barbour County, AL": "01005",
            "Champaign County, IL": "17019",
            "Lancaster County, PA": "42071",
            "Montgomery County, PA": "42091",
            "Story County, IA": "19169",
        }

# ==============================================================================
def format_crop_title(crop_slug):
    return str(crop_slug).replace("_", " ").capitalize()

def to_crop_slug(crop_label):
    slug = crop_label.strip().lower().replace(" ", "_")
    return "sorghum" if slug == "grain_sorghum" else slug

def format_score(score_val, decimals=1):
    if score_val is None:
        return "N/A"
    if decimals == 0:
        return f"{int(round(float(score_val)))}/100"
    return f"{float(score_val):.{decimals}f}"

def get_ideal_rotations_from_backend(fips, first_harvest, planned_rotation, require_family_change, margin_weight):
    c1_raw, c2_raw = [c.strip() for c in planned_rotation.split("->")]
    margin_w = round(margin_weight / 100.0, 2)
    shortfall_w = round((100 - margin_weight) / 100.0, 2)

    payload = {
        "county_fips": str(fips).zfill(5),
        "first_harvest_year": int(first_harvest),
        "horizon_years": 2,
        "weights": {
            "margin": margin_w,
            "lower_rainfed_shortfall": shortfall_w,
        },
        "require_crop_family_change": bool(require_family_change),
        "baseline_rotation": [to_crop_slug(c1_raw), to_crop_slug(c2_raw)],
        "data_mode": "historical",
    }

    try:
        resp = requests.post(
            "http://" + "127.0.0.1:8000/api/v1/rotations/compare",
            json=payload,
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {
            "baseline": {
                "seasons": [
                    {"harvest_year": int(first_harvest), "crop": to_crop_slug(c1_raw)},
                    {"harvest_year": int(first_harvest) + 1, "crop": to_crop_slug(c2_raw)},
                ],
                "annual_margin_usd_per_acre": 145,
                "rainfed_shortfall_mm": 70,
                "score": 0.0,
                "explanation": "Your current rotation.",
            },
            "rotations": [
                {
                    "seasons": [
                        {"harvest_year": int(first_harvest), "crop": "soybeans"},
                        {"harvest_year": int(first_harvest) + 1, "crop": "corn"},
                    ],
                    "annual_margin_usd_per_acre": 150,
                    "rainfed_shortfall_mm": 40,
                    "score": 70.0,
                    "rank": 1,
                    "explanation": "Compared with the baseline: $5 more margin per acre per year, with 30 mm less rainfed shortfall over two years.",
                },
                {
                    "seasons": [
                        {"harvest_year": int(first_harvest), "crop": "sorghum"},
                        {"harvest_year": int(first_harvest) + 1, "crop": "soybeans"},
                    ],
                    "annual_margin_usd_per_acre": 165,
                    "rainfed_shortfall_mm": 50,
                    "score": 63.33,
                    "rank": 2,
                    "explanation": "Compared with the baseline: $20 more margin per acre per year, with 20 mm less rainfed shortfall over two years.",
                },
            ],
        }
# TOP BANNER
st.markdown(
    '<div style="background: linear-gradient(90deg, rgba(26,36,33,0.97) 0%, rgba(26,36,33,0.85) 55%, rgba(65,89,58,0.80) 100%); padding: 16px 26px; border-radius: 10px; margin-bottom: 18px; display: flex; align-items: center; gap: 14px; border-bottom: 3px solid #2E4034;">'
    '<span style="color: #F8F6F0; font-size: 26px; font-weight: 700;">FieldShift</span>'
    '</div>',
    unsafe_allow_html=True,
)
st.markdown("<h1 style='color: #1A2421; font-size: 30px; margin-top: 0; margin-bottom: 16px;'>Compare crop rotations</h1>", unsafe_allow_html=True)

left_col, right_col = st.columns([1.05, 2.35], gap="large")

with left_col:
    county_to_fips = get_us_counties_with_fips()
    county_names = sorted(county_to_fips.keys())
    default_idx = county_names.index("Allen County, KS") if "Allen County, KS" in county_names else 0

    selected_county = st.selectbox("County", options=county_names, index=default_idx, placeholder="type or select your county name")
    selected_fips = county_to_fips[selected_county]
    first_harvest = st.selectbox("First harvest", options=list(range(2024, 2036)), index=0)
    planned_rotation = st.selectbox("Your planned rotation", options=ALL_ROTATIONS, index=0)
    require_family_change = st.checkbox("Requires a crop-family change", value=True)

    st.markdown("<p style='font-size: 12px; font-weight: 700; letter-spacing: 0.8px; margin-top: 14px; margin-bottom: 4px;'>PRIORITIES</p>", unsafe_allow_html=True)
    margin_weight = st.slider("Priority balance", min_value=0, max_value=100, value=35, label_visibility="collapsed")
    shortfall_weight = 100 - margin_weight

    w1, w2 = st.columns(2)
    with w1:
        st.caption(f"**Higher margin: {margin_weight}%**")
    with w2:
        st.markdown(f"<div style='text-align: right; font-size: 12px; color: #555;'>Lower rainfall shortfall: <b>{shortfall_weight}%</b></div>", unsafe_allow_html=True)

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    if st.button("Compare rotations"):
        st.session_state["compare_triggered"] = True

with right_col:
    api_data = get_ideal_rotations_from_backend(selected_fips, first_harvest, planned_rotation, require_family_change, margin_weight)
    base = api_data.get("baseline", {})
    base_crops = [format_crop_title(s.get("crop", "")) for s in base.get("seasons", [])]
    base_name = " -> ".join(base_crops) if base_crops else planned_rotation
    base_margin = base.get("annual_margin_usd_per_acre")
    base_shortfall = base.get("rainfed_shortfall_mm")
    base_score_str = format_score(base.get("score"), decimals=0)
    base_note = base.get("explanation") or "Your current rotation."

    margin_disp = f"${base_margin}/ac/yr" if base_margin is not None else "Margin N/A"
    shortfall_disp = f"{base_shortfall} mm shortfall" if base_shortfall is not None else "Shortfall N/A"

    st.markdown(
        f'<div class="baseline-card"><div>'
        f'<div style="font-size: 16px; font-weight: 700; color: #1A2421;">Your current rotation: {base_name}</div>'
        f'<div style="font-size: 13px; color: #4A4E4D; margin-top: 3px;">{margin_disp} &nbsp;|&nbsp; {shortfall_disp} &nbsp;|&nbsp; <i>{base_note}</i></div>'
        f'</div><div class="score-pill">Score: {base_score_str}</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("<h3 style='font-size: 18px; margin-bottom: 8px; color: #1A2421;'>Top eligible alternatives</h3>", unsafe_allow_html=True)
    rotations = api_data.get("rotations") or []

    if not rotations:
        st.info("No eligible alternative rotations matched your current filters.")
    else:
        h1, h2, h3, h4 = st.columns([2.2, 1.3, 1.3, 1.1])
        h1.caption("**Rotation**")
        h2.caption("**Annual margin**")
        h3.caption("**2-year shortfall**")
        h4.caption("**Score (out of 100)**")

        for idx, rot in enumerate(rotations):
            r_crops = [format_crop_title(s.get("crop", "")) for s in rot.get("seasons", [])]
            r_name = " -> ".join(r_crops)
            r_margin = f"${rot['annual_margin_usd_per_acre']}/ac/yr" if rot.get("annual_margin_usd_per_acre") is not None else "N/A"
            r_shortfall = f"{rot['rainfed_shortfall_mm']} mm" if rot.get("rainfed_shortfall_mm") is not None else "N/A"
            r_score = format_score(rot.get("score"), decimals=1)
            row_class = "alt-row-active" if idx == 0 else "alt-row"
            badge = "* " if idx == 0 else ""

            st.markdown(
                f'<div class="{row_class}" style="display:flex; justify-content:space-between; align-items:center;">'
                f'<div style="flex:2.2; font-weight:700; font-size:15px;">{badge}{r_name}</div>'
                f'<div style="flex:1.3; font-size:14px;">{r_margin}</div>'
                f'<div style="flex:1.3; font-size:14px;">{r_shortfall}</div>'
                f'<div style="flex:1.1; font-weight:700; font-size:15px; text-align:right;">{r_score}</div></div>',
                unsafe_allow_html=True,
            )

        top_rot = rotations
        t_seasons = top_rot.get("seasons", [])
        c1_name = format_crop_title(t_seasons.get("crop", "")) if len(t_seasons) > 0 else "Crop 1"
        c2_name = format_crop_title(t_seasons.get("crop", "")) if len(t_seasons) > 1 else "Crop 2"
        y1_val = t_seasons.get("harvest_year", first_harvest) if len(t_seasons) > 0 else first_harvest
        y2_val = t_seasons.get("harvest_year", first_harvest + 1) if len(t_seasons) > 1 else first_harvest + 1
        c1_fam = CROP_FAMILIES.get(c1_name, "Crop")
        c2_fam = CROP_FAMILIES.get(c2_name, "Crop")
        explanation_text = top_rot.get("explanation") or "Comparison summary unavailable."

        st.markdown(f"<h3 style='font-size:18px; margin-top:16px; margin-bottom:10px; color:#1A2421;'>Ideal crop rotation: {c1_name} -> {c2_name}</h3>", unsafe_allow_html=True)

        card_col1, card_col2 = st.columns(2, gap="medium")
        with card_col1:
            st.markdown(
                f'<div class="crop-stage-card"><div style="font-size:12px; color:#FDF0AC; font-weight:700;">YEAR 1 • {y1_val} HARVEST</div>'
                f'<div style="font-size:22px; font-weight:700; margin-top:4px;">{c1_name}</div>'
                f'<div class="family-tag">{c1_fam}</div></div>',
                unsafe_allow_html=True,
            )
        with card_col2:
            st.markdown(
                f'<div class="crop-stage-card"><div style="font-size:12px; color:#FDF0AC; font-weight:700;">YEAR 2 • {y2_val} HARVEST</div>'
                f'<div style="font-size:22px; font-weight:700; margin-top:4px;">{c2_name}</div>'
                f'<div class="family-tag">{c2_fam}</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown(f'<div class="summary-banner">{explanation_text}</div>', unsafe_allow_html=True)
