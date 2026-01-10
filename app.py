import streamlit as st

# -----------------------------
# Constants
# -----------------------------
LB_TO_KG = 0.453592
KG_TO_LB = 2.20462
MM_TO_IN = 0.0393701

COUPLING_COEFFS = {
    "Downcountry": 0.80,
    "Trail": 0.75,
    "All-Mountain": 0.70,
    "Enduro": 0.78,
    "Long Travel Enduro": 0.92,
    "Downhill (DH)": 0.95,
}

CATEGORY_DEFAULTS = {
    "Downcountry": {"travel": 120, "stroke": 45, "bias": 60, "progression": 10},
    "Trail": {"travel": 140, "stroke": 55, "bias": 63, "progression": 15},
    "All-Mountain": {"travel": 150, "stroke": 60, "bias": 65, "progression": 18},
    "Enduro": {"travel": 170, "stroke": 65, "bias": 68, "progression": 20},
    "Long Travel Enduro": {"travel": 180, "stroke": 70, "bias": 70, "progression": 22},
    "Downhill (DH)": {"travel": 200, "stroke": 75, "bias": 75, "progression": 25},
}

# -----------------------------
# UI
# -----------------------------
st.title("Rear Coil Spring Rate Calculator")

category = st.selectbox("Bike Category", list(CATEGORY_DEFAULTS.keys()))
defaults = CATEGORY_DEFAULTS[category]

unit_mass = st.radio(
    "Mass Units",
    ["Global (kg)", "North America (lbs)"],
    horizontal=True
)

# -----------------------------
# Rider + Gear Mass
# -----------------------------
rider_input = st.number_input(
    "Rider Weight",
    30.0, 150.0,
    75.0,
    step=0.5
)

rider_kg = rider_input * LB_TO_KG if unit_mass == "North America (lbs)" else rider_input

gear_input = st.number_input(
    "Gear Weight (lbs)" if unit_mass == "North America (lbs)" else "Gear Weight (kg)",
    0.0, 25.0,
    4.0,
    step=0.5
)

# ✅ FIX 1 — proper unit handling
gear_kg = gear_input * LB_TO_KG if unit_mass == "North America (lbs)" else gear_input

st.caption("Gear weight is partially coupled to suspension motion depending on category.")

# -----------------------------
# Bike Mass
# -----------------------------
bike_kg = st.number_input(
    "Bike Weight (kg)",
    10.0, 35.0,
    17.0,
    step=0.5
)

unsprung_kg = st.number_input(
    "Unsprung Mass (kg)",
    2.0, 6.0,
    3.5,
    step=0.25
)

# -----------------------------
# Suspension Geometry
# -----------------------------
travel_mm = st.number_input(
    "Rear Wheel Travel (mm)",
    100, 220,
    defaults["travel"],
    step=5
)

stroke_mm = st.selectbox(
    "Shock Stroke (mm)",
    [45, 50, 55, 60, 62.5, 65, 70, 75],
    index=[45, 50, 55, 60, 62.5, 65, 70, 75].index(defaults["stroke"])
)

# -----------------------------
# Kinematics
# -----------------------------
adv_kinematics = st.checkbox("Advanced Kinematics")

# ✅ FIX 3 — defensive initialization
calc_lr_start = travel_mm / stroke_mm if stroke_mm > 0 else 0

if adv_kinematics:
    lr_start = st.number_input(
        "Leverage Ratio Start",
        1.8, 3.5,
        calc_lr_start,
        step=0.05
    )
    prog_pct = st.slider("Progression (%)", 5, 35, defaults["progression"])
    calc_lr_start = lr_start
else:
    prog_pct = defaults["progression"]

# ✅ FIX 4 — simplified, identical math
lr_drop = calc_lr_start * (prog_pct / 100)
lr_end = calc_lr_start - lr_drop
lr_mean = (calc_lr_start + lr_end) / 2

# -----------------------------
# Bias
# -----------------------------
base_bias = defaults["bias"]

# ✅ FIX 2 — prevent clipping
rear_bias = st.slider(
    "Suggested bias (%)",
    55, 80,
    base_bias
)

# -----------------------------
# Sag
# -----------------------------
target_sag = st.slider("Target Sag (%)", 25, 37, 30)

# -----------------------------
# Physics Core
# -----------------------------
eff_rider_kg = rider_kg + (gear_kg * COUPLING_COEFFS[category])
system_kg = eff_rider_kg + bike_kg

rear_sprung_kg = (system_kg * (rear_bias / 100)) - unsprung_kg
rear_sprung_lbs = rear_sprung_kg * KG_TO_LB

stroke_in = stroke_mm * MM_TO_IN
sag_in = stroke_in * (target_sag / 100)

raw_rate = (rear_sprung_lbs * lr_mean) / sag_in

# -----------------------------
# Output
# -----------------------------
st.subheader("Results")

st.metric("Raw Calculated Spring Rate", f"{raw_rate:.1f} lbs/in")

recommended_rate = round(raw_rate / 25) * 25
st.metric("Recommended Spring Rate", f"{recommended_rate} lbs/in")
