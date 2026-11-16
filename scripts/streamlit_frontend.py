import streamlit as st
import os
import sys
from pathlib import Path
from html import escape

ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from scripts.fieldshift_client import BackendError, FieldShiftClient, build_payload

st.set_page_config(page_title="FieldShift - Compare Crop Rotations", layout="wide")

st.markdown("""
<style>
/* GLOBAL FONT */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] *,
[data-testid="stSidebar"] * {
    font-family: Arial, Helvetica, sans-serif !important;
}

/* MAIN BACKGROUND */
[data-testid="stAppViewContainer"],
[data-testid="stHeader"] {
    background-color: #F8F6F0 !important;
}

/* DEFAULT TEXT COLORS */
[data-testid="stAppViewContainer"] {
    color: #1A2421 !important;
}

[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3,
[data-testid="stWidgetLabel"],
[data-testid="stMarkdownContainer"] {
    color: #1A2421 !important;
}

/* SPACING */
.block-container {
    padding-top: 2rem !important;
    padding-bottom: 2rem !important;
}

/* DROPDOWNS */
div[data-baseweb="select"] > div {
    background-color: #FFFFFF !important;
    border: 1px solid #C8C4B8 !important;
    border-radius: 6px !important;
    color: #1A2421 !important;
}

div[data-baseweb="select"] span,
div[data-baseweb="select"] input {
    color: #1A2421 !important;
}

/* DROPDOWN OPTIONS */
div[data-baseweb="popover"],
div[data-baseweb="popover"] * {
    color: #1A2421 !important;
}

div[data-baseweb="popover"] li {
    background-color: #FFFFFF !important;
}

/* BUTTONS */
.stButton > button,
.stFormSubmitButton > button {
    background-color: #1A2421 !important;
    color: #F8F6F0 !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 0.55rem 1rem !important;
    font-weight: 600 !important;
    width: 100%;
}

.stButton > button *,
.stFormSubmitButton > button * {
    color: #F8F6F0 !important;
}

.stButton > button:hover,
.stFormSubmitButton > button:hover {
    background-color: #2B3B36 !important;
    color: #FDF0AC !important;
}

.stButton > button:hover *,
.stFormSubmitButton > button:hover * {
    color: #FDF0AC !important;
}

/* BASELINE CARD */
.baseline-card {
    background-color: #EAE6D9;
    border: 1px solid #D5D0C0;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: #1A2421 !important;
}

.baseline-card div:not(.score-pill) {
    color: #1A2421;
}

/* SCORE PILL */
.score-pill {
    background-color: #1A2421;
    color: #FDF0AC !important;
    font-weight: 700;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 15px;
}

/* ALTERNATIVE ROWS */
.alt-row {
    background-color: #FFFFFF;
    border: 1px solid #DCD8CA;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 10px;
    color: #1A2421 !important;
}

.alt-row-active {
    background-color: #FDF0AC;
    border: 1.5px solid #1A2421;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 10px;
    color: #1A2421 !important;
}

.alt-row div,
.alt-row-active div {
    color: #1A2421 !important;
}

/* CROP STAGE CARDS */
.crop-stage-card {
    background-color: #1A2421;
    color: #F8F6F0 !important;
    border-radius: 10px;
    padding: 20px;
    border-bottom: 4px solid #FDF0AC;
}

.crop-stage-card div:not(.family-tag) {
    color: #F8F6F0 !important;
}

/* FAMILY TAG */
.family-tag {
    display: inline-block;
    background-color: #FDF0AC;
    color: #1A2421 !important;
    font-size: 11px;
    font-weight: 700;
    padding: 3px 9px;
    border-radius: 4px;
    margin-top: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* SUMMARY BANNER */
.summary-banner {
    background-color: #EAE6D9;
    border-left: 4px solid #1A2421;
    padding: 12px 16px;
    border-radius: 6px;
    margin-top: 16px;
    font-size: 14px;
    color: #1A2421 !important;
}

/* CAPTIONS AND SLIDER LABELS */
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] *,
[data-testid="stSlider"] p,
[data-testid="stCheckbox"] p {
    color: #1A2421 !important;
}

/* INFO AND EXPANDER TEXT */
[data-testid="stAlert"] p,
[data-testid="stExpander"] p {
    color: #1A2421 !important;
}
    .outcome-notes {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 18px;
        margin: 0 0 18px;
        color: #4A4E4D;
        font-size: 12px;
        line-height: 1.5;
    }
    .outcome-notes strong {
        display: block;
        color: #1A2421;
        font-size: 13px;
        margin-bottom: 3px;
    }
    .priority-labels {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 24px;
        font-size: 14px;
        font-weight: 700;
        line-height: 1.5;
        color: #1A2421;
        margin-bottom: 12px;
    }
    .priority-labels span:first-child {
        text-align: left;
    }
    .priority-labels span:last-child {
        text-align: right;
    }
    @media (max-width: 640px) {
        .outcome-notes { grid-template-columns: 1fr; gap: 10px; }
    }
    </style>
""", unsafe_allow_html=True)

CROP_FAMILIES = {"Corn": "Grass / Cereal", "Soybeans": "Legume"}

@st.cache_data(ttl=60, show_spinner=False)
def get_supported_counties(mode, base_url):
    client = FieldShiftClient(mode=mode, base_url=base_url)
    capabilities = client.capabilities()
    return capabilities["planning"]["supported_ml_counties"], client.mode

def format_crop_title(crop_slug):
    return str(crop_slug).replace("_", " ").capitalize()

def format_score(score_val, decimals=1):
    if score_val is None:
        return "N/A"
    return f"{float(score_val):.{decimals}f}"

# TOP BANNER
st.markdown(
    '<div style="background: linear-gradient(90deg, rgba(26,36,33,0.97) 0%, rgba(26,36,33,0.85) 55%, rgba(65,89,58,0.80) 100%); padding: 16px 26px; border-radius: 10px; margin-bottom: 18px; display: flex; align-items: center; gap: 14px; border-bottom: 3px solid #2E4034;">'
    '<span style="color: #F8F6F0; font-size: 26px; font-weight: 700;">FieldShift</span>'
    '</div>',
    unsafe_allow_html=True,
)
title_col, notes_col = st.columns([1.05, 2.35], gap="large")
with title_col:
    st.markdown("<h1 style='color: #1A2421; font-size: 30px; margin-top: 0; margin-bottom: 16px;'>Compare crop rotations</h1>", unsafe_allow_html=True)
    st.caption("Two-year rotation comparison based on historical weather scenarios.")
with notes_col:
    st.markdown(
        '<div class="outcome-notes">'
        '<div><strong>Annual margin</strong>'
        'Predicted yield &times; crop price &minus; production cost, averaged per acre per year across historical scenarios. '
        'Negative values mean modeled costs exceed revenue.</div>'
        '<div><strong>Water shortfall</strong>'
        'Crop water demand left unmet by rainfall and stored soil water. '
        'Two-year totals are averaged across historical scenarios.</div>'
        '<div><strong>Score (0&ndash;100)</strong>'
        'Margin and shortfall are scaled against eligible plans, then combined using your priority weights. '
        'Higher is better.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

left_col, right_col = st.columns([1.05, 2.35], gap="large")

with left_col:
    configured_mode = os.getenv("FIELDSHIFT_BACKEND_MODE", "auto")
    api_url = os.getenv("FIELDSHIFT_API_URL", "http://127.0.0.1:8000")
    try:
        county_entries, backend_mode = get_supported_counties(configured_mode, api_url)
    except BackendError as error:
        st.error(str(error))
        st.stop()
    counties_by_label = {entry["county_label"]: entry for entry in county_entries}
    county_names = sorted(counties_by_label)
    default_idx = county_names.index("Allen County, KS") if "Allen County, KS" in county_names else 0
    with st.form("rotation_comparison"):
        selected_county = st.selectbox("County", options=county_names, index=default_idx)
        selected = counties_by_label[selected_county]
        selected_fips = selected["county_fips"]
        # Required by the API; historical scenario calculations do not depend on this label.
        first_harvest = 2026
        crops = [format_crop_title(crop) for crop in selected["crops"] if crop in ("corn", "soybeans")]
        rotations = [f"{first} -> {second}" for first in crops for second in crops]
        planned_rotation = st.selectbox("Your planned rotation", options=rotations, index=0)
        require_family_change = st.checkbox("Requires a crop-family change", value=True)
        st.markdown("<p style='font-size:12px;font-weight:700;margin-top:14px;'>PRIORITIES</p>", unsafe_allow_html=True)
        margin_weight = st.slider("Profit priority (%)", min_value=0, max_value=100, value=35, label_visibility="collapsed")
        st.markdown(
            '<div class="priority-labels">'
            f'<span>Favor lower water shortfall: <b>{100 - margin_weight}%</b></span>'
            f'<span>Favor profit: <b>{margin_weight}%</b></span>'
            '</div>',
            unsafe_allow_html=True,
        )
        compare_clicked = st.form_submit_button("Compare rotations")

with right_col:
    if compare_clicked:
        payload = build_payload(selected_fips, first_harvest, planned_rotation, require_family_change, margin_weight)
        st.session_state["api_data"] = None
        st.session_state["api_error"] = None
        with st.spinner("Comparing crop rotations..."):
            try:
                result = FieldShiftClient(mode=backend_mode, base_url=api_url).compare(payload)
                st.session_state["api_data"] = result
                st.session_state["submitted_request"] = payload
            except BackendError as error:
                st.session_state["api_error"] = str(error)

    if st.session_state.get("api_error"):
        st.error(st.session_state["api_error"])
        st.stop()
    api_data = st.session_state.get("api_data")
    if api_data is None:
        st.info("Choose your county and priorities, then select Compare rotations.")
        st.stop()
    submitted = st.session_state["submitted_request"]
    st.caption(
        f'{api_data["county_label"]} | Two-year rotation | '
        f'Margin priority {submitted["weights"]["margin"]:.0%}'
    )
    base = api_data.get("baseline", {})
    base_crops = [format_crop_title(s.get("crop", "")) for s in base.get("seasons", [])]
    base_name = " -> ".join(base_crops) if base_crops else planned_rotation
    base_margin = base.get("annual_margin_usd_per_acre")
    base_shortfall = base.get("rainfed_shortfall_mm")
    margin_disp = f"${float(base_margin):,.2f}/ac/yr" if base_margin is not None else "Margin N/A"
    shortfall_disp = f"{float(base_shortfall):,.1f} mm shortfall" if base_shortfall is not None else "Shortfall N/A"
    base_score_str = format_score(base.get("score"), decimals=1)
    base_note = escape(base.get("explanation") or "Your current rotation.")

    st.markdown(
        f'<div class="baseline-card"><div>'
        f'<div style="font-size: 16px; font-weight: 700; color: #1A2421;">Your current rotation: {base_name}</div>'
        f'<div style="font-size: 13px; color: #4A4E4D; margin-top: 3px;">{margin_disp} &nbsp;|&nbsp; {shortfall_disp} &nbsp;|&nbsp; <i>{base_note}</i></div>'
        f'</div><div class="score-pill">Score: {base_score_str}/100</div></div>',
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
            r_margin = f"${float(rot['annual_margin_usd_per_acre']):,.2f}/ac/yr" if rot.get("annual_margin_usd_per_acre") is not None else "N/A"
            r_shortfall = f"{float(rot['rainfed_shortfall_mm']):,.1f} mm" if rot.get("rainfed_shortfall_mm") is not None else "N/A"
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

        top_rot = rotations[0]
        t_seasons = top_rot.get("seasons", [])
        c1_name = format_crop_title(t_seasons[0].get("crop", "")) if len(t_seasons) > 0 else "Crop 1"
        c2_name = format_crop_title(t_seasons[1].get("crop", "")) if len(t_seasons) > 1 else "Crop 2"
        c1_fam = CROP_FAMILIES.get(c1_name, "Crop")
        c2_fam = CROP_FAMILIES.get(c2_name, "Crop")
        explanation_text = escape(top_rot.get("explanation") or "Comparison summary unavailable.")

        st.markdown(f"<h3 style='font-size:18px; margin-top:16px; margin-bottom:10px; color:#1A2421;'>Top-ranked alternative: {c1_name} -> {c2_name}</h3>", unsafe_allow_html=True)

        card_col1, card_col2 = st.columns(2, gap="medium")
        with card_col1:
            st.markdown(
                f'<div class="crop-stage-card"><div style="font-size:12px; color:#FDF0AC; font-weight:700;">YEAR 1</div>'
                f'<div style="font-size:22px; font-weight:700; margin-top:4px;">{c1_name}</div>'
                f'<div class="family-tag">{c1_fam}</div></div>',
                unsafe_allow_html=True,
            )
        with card_col2:
            st.markdown(
                f'<div class="crop-stage-card"><div style="font-size:12px; color:#FDF0AC; font-weight:700;">YEAR 2</div>'
                f'<div style="font-size:22px; font-weight:700; margin-top:4px;">{c2_name}</div>'
                f'<div class="family-tag">{c2_fam}</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown(f'<div class="summary-banner">{explanation_text}</div>', unsafe_allow_html=True)
    with st.expander("Scenario and budget assumptions"):
        st.write(api_data.get("economics_assumptions", ""))
        pairs = api_data.get("historical_pairs", [])
        st.write("Historical scenarios: " + ", ".join(f"{a}–{b}" for a, b in pairs))
        for assumption in api_data.get("assumptions", []):
            st.write("• " + assumption)

