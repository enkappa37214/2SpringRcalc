import streamlit as st
import pandas as pd
import math

# ==========================================================
# 1. CONFIGURATION & DATA CONSTANTS
# ==========================================================
st.set_page_config(page_title="Pro MTB Spring Rate Calculator", page_icon="⚙️", layout="centered")

# --- Constants ---
LB_TO_KG = 0.453592
KG_TO_LB = 2.20462
IN_TO_MM = 25.4
MM_TO_IN = 1/25.4
STONE_TO_KG = 6.35029

# Physics Tuning Constants
PROGRESSIVE_CORRECTION_FACTOR = 0.97  # Reduces rate by 3% for progressive coils

# --- Data Tables ---
CATEGORY_DATA = {
    "Downcountry": {
        "travel": 115, "stroke": 45.0, "base_sag": 28,
        "progression": 12, "lr_start": 2.75, "desc": "110–120 mm", "bike_mass_def_kg": 12.0, "bias": 60
    },
    "Trail": {
        "travel": 130, "stroke": 50.0, "base_sag": 30,
        "progression": 15, "lr_start": 2.80, "desc": "120–140 mm", "bike_mass_def_kg": 13.5, "bias": 63
    },
    "All-Mountain": {
        "travel": 145, "stroke": 55.0, "base_sag": 31,
        "progression": 18, "lr_start": 2.90, "desc": "140–150 mm", "bike_mass_def_kg": 14.5, "bias": 65
    },
    "Enduro": {
        "travel": 160, "stroke": 62.5, "base_sag": 33,
        "progression": 22, "lr_start": 3.00, "desc": "150–170 mm", "bike_mass_def_kg": 15.11, "bias": 67
    },
    "Long Travel Enduro": {
        "travel": 175, "stroke": 65.0, "base_sag": 34,
        "progression": 25, "lr_start": 3.05, "desc": "170–180 mm", "bike_mass_def_kg": 16.5, "bias": 69
    },
    "Enduro (Race focus)": {
        "travel": 165, "stroke": 62.5, "base_sag": 32,
        "progression": 26, "lr_start": 3.13, "desc": "160–170 mm", "bike_mass_def_kg": 15.8, "bias": 68
    },
    "Downhill (DH)": {
        "travel": 200, "stroke": 75.0, "base_sag": 35,
        "progression": 30, "lr_start": 3.14, "desc": "180–210 mm", "bike_mass_def_kg": 17.5, "bias": 72
    }
}

SKILL_MODIFIERS = {
    "Just starting": {"bias": +4},
    "Beginner":      {"bias": +2},
    "Intermediate":  {"bias": 0},
    "Advanced":      {"bias": -1},
    "Racer":         {"bias": -2}
}
SKILL_LEVELS = list(SKILL_MODIFIERS.keys())

COUPLING_COEFFS = {
    "Downcountry": 0.80, "Trail": 0.75, "All-Mountain": 0.70,
    "Enduro": 0.72, "Long Travel Enduro": 0.90,
    "Enduro (Race focus)": 0.78, "Downhill (DH)": 0.95
}

SIZE_WEIGHT_MODS = {"XS": -0.5, "S": -0.25, "M": 0.0, "L": 0.3, "XL": 0.6, "XXL": 0.95}

BIKE_WEIGHT_EST = {
    "Downcountry": {"Carbon": [12.2, 11.4, 10.4], "Aluminium": [13.8, 13.1, 12.5]},
    "Trail":       {"Carbon": [14.1, 13.4, 12.8], "Aluminium": [15.4, 14.7, 14.0]},
    "All-Mountain":{"Carbon": [15.0, 14.2, 13.5], "Aluminium": [16.2, 15.5, 14.8]},
    "Enduro":      {"Carbon": [16.2, 15.5, 14.8], "Aluminium": [17.5, 16.6, 15.8]},
    "Long Travel Enduro": {"Carbon": [16.8, 16.0, 15.2], "Aluminium": [18.0, 17.2, 16.5]},
    "Enduro (Race focus)": {"Carbon": [16.0, 15.2, 14.5], "Aluminium": [17.2, 16.3, 15.5]},
    "Downhill (DH)": {"Carbon": [17.8, 17.0, 16.2], "Aluminium": [19.5, 18.5, 17.5]}
}

SPRINDEX_DATA = {
    "XC/Trail (55mm)": {"max_stroke": 55, "ranges": ["380-430", "430-500", "490-560", "550-610", "610-690", "650-760"]},
    "Enduro (65mm)":   {"max_stroke": 65, "ranges": ["340-380", "390-430", "450-500", "500-550", "540-610", "610-700"]},
    "DH (75mm)":       {"max_stroke": 75, "ranges": ["290-320", "340-370", "400-440", "450-490", "510-570", "570-630"]}
}

COMMON_STROKES = [37.5, 40.0, 42.5, 45.0, 47.5, 50.0, 52.5, 55.0, 57.5, 60.0, 62.5, 65.0, 70.0, 72.5, 75.0]

# ==========================================================
# 2. HELPER FUNCTIONS
# ==========================================================
@st.cache_data
def load_bike_database():
    try:
        # Assumes file is in same directory
        df = pd.read_csv("clean_suspension_database.csv")
        # Ensure numbers are floats
        cols = ['Travel_mm', 'Shock_Stroke', 'Start_Leverage', 'End_Leverage', 'Progression_Pct']
        for c in cols:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        return df.sort_values('Model')
    except FileNotFoundError:
        return pd.DataFrame()

def estimate_unsprung(wheel_tier, frame_mat, has_inserts):
    base = 1.0
    wheels = {"Light": 1.7, "Standard": 2.3, "Heavy": 3.0}[wheel_tier]
    swingarm = 0.4 if frame_mat == "Carbon" else 0.7
    inserts = 0.5 if has_inserts else 0.0
    return base + wheels + swingarm + inserts

def analyze_spring_compatibility(progression_pct, has_hbo):
    analysis = {
        "Linear": {"status": "", "msg": ""},
        "Progressive": {"status": "", "msg": ""}
    }
    if progression_pct > 25:
        analysis["Linear"]["status"] = "✅ Optimal"
        analysis["Linear"]["msg"] = "Matches frame kinematics perfectly."
        analysis["Progressive"]["status"] = "⚠️ Avoid"
        analysis["Progressive"]["msg"] = "Risk of harsh 'Wall Effect' at bottom-out."
    elif 12 <= progression_pct <= 25:
        analysis["Linear"]["status"] = "✅ Compatible"
        analysis["Linear"]["msg"] = "Use for a consistent, planted, and plush coil feel."
        analysis["Progressive"]["status"] = "✅ Compatible"
        analysis["Progressive"]["msg"] = "Use for more 'pop' and extra bottom-out resistance (Air-shock feel)."
        if has_hbo:
            analysis["Linear"]["msg"] += " (HBO handles the bottom-out)."
    else:
        analysis["Linear"]["status"] = "⚠️ Caution"
        analysis["Linear"]["msg"] = "High risk of harsh bottom-outs unless shock has strong HBO."
        analysis["Progressive"]["status"] = "✅ Optimal"
        analysis["Progressive"]["msg"] = "Essential to compensate for the frame's lack of ramp-up."
    return analysis

# ==========================================================
# 3. SESSION STATE & CALLBACKS
# ==========================================================
if 'last_category' not in st.session_state:
    st.session_state.last_category = None

def reset_chassis():
    for key in ['bike_weight_man', 'rear_bias_slider']:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.last_category = None

# ==========================================================
# 4. MAIN UI START
# ==========================================================
st.title("Pro MTB Spring Rate Calculator")

# Load Database
bike_db = load_bike_database()

# --- SETTINGS ---
with st.expander("⚙️ Settings & Units", expanded=False):
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        unit_mass = st.radio("Mass Units", ["Global (kg)", "North America (lbs)", "UK Hybrid (st & kg)"])
    with col_u2:
        unit_len = st.radio("Length Units", ["Millimetres (mm)", "Inches (\")"])

# ==========================================================
# 5. UI - RIDER
# ==========================================================
st.header("1. Rider Profile")
col_r1, col_r2 = st.columns(2)

with col_r1:
    skill = st.selectbox("Rider Skill", SKILL_LEVELS, index=2)

with col_r2:
    if unit_mass == "UK Hybrid (st & kg)":
        stone = st.number_input("Rider Weight (st)", 5.0, 20.0, 11.0, 0.5)
        lbs_rem = st.number_input("Rider Weight (+lbs)", 0.0, 13.9, 0.0, 1.0)
        rider_kg = (stone * STONE_TO_KG) + (lbs_rem * LB_TO_KG)
        st.caption(f"Total: {rider_kg:.1f} kg")
    elif unit_mass == "North America (lbs)":
        rider_in = st.number_input("Rider Weight (lbs)", 90.0, 280.0, 160.0, 1.0)
        rider_kg = rider_in * LB_TO_KG
    else:
        rider_in = st.number_input("Rider Weight (kg)", 40.0, 130.0, 68.0, 0.5)
        rider_kg = rider_in

    gear_label = "Gear Weight (lbs)" if unit_mass == "North America (lbs)" else "Gear Weight (kg)"
    gear_def = 5.0 if unit_mass == "North America (lbs)" else 4.0
    gear_in = st.number_input(gear_label, 0.0, 25.0, gear_def, 0.5)
    gear_kg = gear_in * LB_TO_KG if "lbs" in unit_mass else gear_in

# ==========================================================
# 6. UI - CHASSIS
# ==========================================================
st.header("2. Chassis Data")

# --- DATABASE SELECTION ---
selected_bike_data = None
is_db_bike = False

if not bike_db.empty:
    bike_models = ["Select Manually / Not Found"] + list(bike_db['Model'].unique())
    selected_model = st.selectbox("🚲 Select Bike Model (Auto-Fill)", bike_models)
    
    if selected_model != "Select Manually / Not Found":
        selected_bike_data = bike_db[bike_db['Model'] == selected_model].iloc[0]
        is_db_bike = True
        st.success(f"Loaded data for **{selected_model}**: {selected_bike_data['Travel_mm']:.0f}mm Travel | {selected_bike_data['Progression_Pct']:.1f}% Progression")
else:
    st.warning("Database file not found. Using Manual Mode.")

cat_options = list(CATEGORY_DATA.keys())
cat_labels = [f"{k} ({CATEGORY_DATA[k]['desc']})" for k in cat_options]

# Auto-select category based on travel if bike is selected
default_cat_index = 3 # Enduro
if is_db_bike:
    t = selected_bike_data['Travel_mm']
    if t < 125: default_cat_index = 0 # Downcountry
    elif t < 140: default_cat_index = 1 # Trail
    elif t < 155: default_cat_index = 2 # All Mtn
    elif t < 170: default_cat_index = 3 # Enduro
    elif t < 185: default_cat_index = 4 # Long Travel
    else: default_cat_index = 6 # DH

selected_idx = st.selectbox(
    "Category (Determines Weight Bias)",
    range(len(cat_options)),
    format_func=lambda x: cat_labels[x],
    key='category_select',
    index=default_cat_index
)
category = cat_options[selected_idx]
defaults = CATEGORY_DATA[category]

col_c1, col_c2 = st.columns(2)

# --- Bike Weight ---
with col_c1:
    weight_mode = st.radio("Bike Weight Mode", ["Manual Input", "Estimate"], index=0, horizontal=True)
    if weight_mode == "Estimate":
        mat = st.selectbox("Frame Material", ["Carbon", "Aluminium"])
        level = st.selectbox("Build Level", ["Entry-Level", "Mid-Level", "High-End"])
        size = st.selectbox("Size", list(SIZE_WEIGHT_MODS.keys()), index=2)
        
        level_idx = {"Entry-Level": 0, "Mid-Level": 1, "High-End": 2}[level]
        base_w = BIKE_WEIGHT_EST[category][mat][level_idx]
        est_w = base_w + SIZE_WEIGHT_MODS[size]
        st.info(f"Estimated: {est_w:.2f} kg ({est_w * KG_TO_LB:.1f} lbs)")
        bike_kg = est_w
    else:
        is_lbs = unit_mass == "North America (lbs)"
        lbl = "Bike Weight (lbs)" if is_lbs else "Bike Weight (kg)"
        def_w_kg = defaults.get("bike_mass_def_kg", 14.5)
        def_w_val = def_w_kg * KG_TO_LB if is_lbs else def_w_kg
        min_w, max_w = (15.0, 66.0) if is_lbs else (7.0, 30.0)
        w_in = st.number_input(lbl, min_w, max_w, float(def_w_val), 0.1, key="bike_weight_man")
        bike_kg = w_in * LB_TO_KG if is_lbs else w_in

# --- Rear Bias ---
with col_c2:
    cat_def_bias = int(defaults["bias"])
    skill_suggestion = SKILL_MODIFIERS[skill]["bias"]
    
    if 'rear_bias_slider' not in st.session_state:
        st.session_state.rear_bias_slider = cat_def_bias
        
    rear_bias_in = st.slider("Rear Weight Bias (%)", 55, 85, key="rear_bias_slider")
    
    final_bias_calc = rear_bias_in
    if skill_suggestion != 0:
        advice_sign = "+" if skill_suggestion > 0 else ""
        st.caption(f"Skill Tip: **{skill}** suggests **{advice_sign}{skill_suggestion}%** bias.")

# --- Unsprung Mass ---
with col_c1:
    unsprung_mode = st.toggle("Estimate Unsprung Mass", value=False)
    if unsprung_mode:
        u_tier = st.selectbox("Wheelset Tier", ["Light", "Standard", "Heavy"], index=1)
        u_mat = st.selectbox("Rear Triangle", ["Carbon", "Aluminium"], index=1)
        has_inserts = st.checkbox("Tyre Inserts installed?", value=False)
        unsprung_kg = estimate_unsprung(u_tier, u_mat, has_inserts)
        st.caption(f"Est: {unsprung_kg:.1f} kg")
    else:
        is_lbs = unit_mass == "North America (lbs)"
        lbl_u = "Unsprung (lbs)" if is_lbs else "Unsprung (kg)"
        u_def = 9.4 if is_lbs else 4.27
        u_in = st.number_input(lbl_u, 0.0, 20.0, u_def, 0.01)
        unsprung_kg = u_in * LB_TO_KG if is_lbs else u_in

# ==========================================================
# 7. SHOCK & KINEMATICS
# ==========================================================
st.header("3. Shock & Kinematics")
col_k1, col_k2 = st.columns(2)

# Determine defaults (Database vs Category)
if is_db_bike:
    raw_travel = float(selected_bike_data['Travel_mm'])
    raw_stroke = float(selected_bike_data['Shock_Stroke'])
    raw_prog = float(selected_bike_data['Progression_Pct'])
    raw_lr_start = float(selected_bike_data['Start_Leverage'])
    raw_lr_end = float(selected_bike_data['End_Leverage'])
else:
    raw_travel = defaults["travel"]
    raw_stroke = defaults["stroke"]
    raw_prog = float(defaults["progression"])
    raw_lr_start = float(defaults["lr_start"])
    raw_lr_end = raw_lr_start * (1 - (raw_prog/100))

# Unit Conversion for Display
def_travel = raw_travel if unit_len == "Millimetres (mm)" else raw_travel * MM_TO_IN
def_stroke = raw_stroke if unit_len == "Millimetres (mm)" else raw_stroke * MM_TO_IN

with col_k1:
    t_lbl = "Rear Travel (mm)" if unit_len == "Millimetres (mm)" else "Rear Travel (in)"
    travel_in = st.number_input(t_lbl, 0.0, 300.0, float(def_travel), 1.0)
    
    s_lbl = "Shock Stroke (mm)" if unit_len == "Millimetres (mm)" else "Shock Stroke (in)"
    stroke_in = st.number_input(s_lbl, 1.5, 100.0, float(def_stroke), 0.5)

travel_mm = travel_in * IN_TO_MM if unit_len != "Millimetres (mm)" else travel_in
stroke_mm = stroke_in * IN_TO_MM if unit_len != "Millimetres (mm)" else stroke_in

# Calc variables
calc_lr_start = 0.0
calc_lr_end = 0.0
use_advanced_calc = False

with col_k2:
    # Auto-check Advanced Kinematics if we have DB data or user wants it
    adv_kinematics = st.checkbox("Advanced Kinematics (Leverage Ratio)", value=is_db_bike)
    
    if adv_kinematics:
        use_advanced_calc = True
        
        lr_start = st.number_input("LR Start Rate", 1.5, 4.0, raw_lr_start, 0.05)
        
        # If DB bike, we likely have End Rate directly. If manual, allow toggle.
        k_input_mode = st.radio("Input Mode", ["Start & End Rates", "Start & Progression %"], horizontal=True, index=0)
        
        if k_input_mode == "Start & Progression %":
            prog_pct = st.number_input("Progression (%)", -10.0, 60.0, raw_prog, 1.0)
            lr_end = lr_start * (1 - (prog_pct/100))
            st.caption(f"Derived End Rate: {lr_end:.2f}")
        else:
            lr_end = st.number_input("LR End Rate", 1.5, 4.0, raw_lr_end, 0.05)
            # Avoid division by zero
            if lr_start > 0:
                prog_pct = ((lr_start - lr_end) / lr_start) * 100
            else:
                prog_pct = 0
            st.caption(f"Calculated Progression: {prog_pct:.1f}%")

        calc_lr_start = lr_start
        calc_lr_end = lr_end
        
    else:
        # Simple Mode
        prog_pct = float(defaults["progression"])
        if stroke_mm > 0:
            mean_lr = travel_mm / stroke_mm
            st.metric("Mean Leverage Ratio", f"{mean_lr:.2f}")
        else:
            mean_lr = 0
    
    has_hbo = st.checkbox("Shock has HBO (Hydraulic Bottom Out)?")

# Springs You Can Use Display
analysis = analyze_spring_compatibility(prog_pct, has_hbo)
st.subheader("Springs You Can Use")
for spring_type, info in analysis.items():
    if "Avoid" in info["status"] or "Caution" in info["status"]:
        st.markdown(f"❌ **{spring_type}**: {info['msg']}")
    else:
        st.markdown(f"**{info['status']} {spring_type}**: {info['msg']}")

# Selection for Calculation
spring_type_options = ["Standard Steel (Linear)", "Lightweight Steel/Ti", "Sprindex", "Progressive Coil"]
spring_type_sel = st.selectbox("Select Spring for Calculation", spring_type_options, index=0)
active_spring_type = spring_type_sel

# ==========================================================
# 8. CALCULATIONS
# ==========================================================
st.header("4. Setup Preferences")
smart_default_sag = defaults["base_sag"]
target_sag = st.slider(
    "Target Sag (%)", 
    min_value=20.0, max_value=40.0, 
    value=float(smart_default_sag), 
    step=0.5
)

if use_advanced_calc:
    total_drop = calc_lr_start - calc_lr_end
    effective_lr = calc_lr_start - (total_drop * (target_sag / 100))
else:
    if stroke_mm > 0:
        effective_lr = travel_mm / stroke_mm
    else:
        effective_lr = 1.0

coupling = COUPLING_COEFFS[category]
eff_rider_kg = rider_kg + (gear_kg * coupling)
system_kg = eff_rider_kg + bike_kg
rear_load_kg = (system_kg * (final_bias_calc / 100)) - unsprung_kg
rear_load_lbs = rear_load_kg * KG_TO_LB

if stroke_mm > 0:
    sag_mm = stroke_mm * (target_sag / 100)
    raw_rate = (rear_load_lbs * effective_lr) / (sag_mm * MM_TO_IN)
else:
    sag_mm = 0
    raw_rate = 0

if active_spring_type == "Progressive Coil":
    raw_rate = raw_rate * PROGRESSIVE_CORRECTION_FACTOR

# ==========================================================
# 9. OUTPUTS
# ==========================================================
st.divider()
st.header("Results")

if raw_rate > 0:
    res_c1, res_c2 = st.columns(2)
    res_c1.metric("Ideal Spring Rate", f"{int(raw_rate)} lbs/in")
    res_c2.metric("Target Sag", f"{target_sag:.1f}% ({sag_mm:.1f} mm)")

    # Initialize default tuning variable
    final_rate_for_tuning = int(round(raw_rate / 25) * 25)

    # --- CONDITIONAL DISPLAY LOGIC ---
    if active_spring_type == "Sprindex":
        st.subheader("Sprindex Recommendation")
        
        family = None
        if stroke_mm <= 55: family = "XC/Trail (55mm)"
        elif stroke_mm <= 65: family = "Enduro (65mm)"
        elif stroke_mm <= 75: family = "DH (75mm)"
        
        if family:
            st.markdown(f"**Compatible Family:** {family}")
            ranges = SPRINDEX_DATA[family]["ranges"]
            found_match = False
            
            for r_str in ranges:
                low, high = map(int, r_str.split("-"))
                if low <= raw_rate <= high:
                    st.success(f"✅ **Perfect Fit:** {r_str} lbs/in")
                    spr_rounded = int(round(raw_rate / 5) * 5)
                    final_rate_for_tuning = spr_rounded
                    found_match = True
                    break
            
            if not found_match:
                st.warning("Calculated rate is outside standard Sprindex ranges for this stroke length.")
                final_rate_for_tuning = int(raw_rate)
        else:
            st.error(f"Shock stroke ({stroke_mm}mm) exceeds Sprindex maximums.")
            final_rate_for_tuning = int(raw_rate)

    else:
        # --- STANDARD DISPLAY ---
        st.subheader("Available Spring Options")
        options = []
        base_step = 25
        center_rate = int(round(raw_rate / base_step) * base_step)
        final_rate_for_tuning = center_rate
        rates_to_check = [center_rate - base_step, center_rate, center_rate + base_step]

        for rate in rates_to_check:
            if rate <= 0: continue
            resulting_sag_mm = (rear_load_lbs * effective_lr) / (rate * MM_TO_IN) 
            resulting_sag_pct = (resulting_sag_mm / stroke_mm) * 100
            
            tag = ""
            if rate == center_rate: tag = "✅ Recommended"
            elif resulting_sag_pct > 35: tag = "⚠️ Too Soft"
            elif resulting_sag_pct < 25: tag = "⚠️ Too Stiff"
            else: tag = "Alternative"

            options.append({
                "Spring Rate": f"{rate} lbs",
                "Resulting Sag (%)": f"{resulting_sag_pct:.1f}%",
                "Travel Usage (mm)": f"{resulting_sag_mm:.1f} mm",
                "Fit": tag
            })

        df_options = pd.DataFrame(options)
        st.dataframe(df_options.style.apply(lambda x: ['background-color: #d4edda' if 'Recommended' in v else '' for v in x], subset=['Fit']), hide_index=True)

    st.subheader("Fine Tuning (Preload)")
    st.caption(f"Effect of preload on the **{final_rate_for_tuning} lbs** spring:")

    preload_data = []
    for turns in [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        preload_mm = turns * 1.0 
        preload_in = preload_mm * MM_TO_IN
        sag_in_eff = (rear_load_lbs * effective_lr / final_rate_for_tuning) - preload_in
        sag_pct_eff = (sag_in_eff / (stroke_mm * MM_TO_IN)) * 100
        
        status = "✅"
        if turns >= 3.0: status = "⚠️ Excessive"
        elif sag_pct_eff < 25: status = "⚠️ Too Stiff"
        
        preload_data.append({
            "Turns": turns,
            "Sag (%)": f"{sag_pct_eff:.1f}%",
            "Sag (mm)": f"{(sag_pct_eff/100)*stroke_mm:.1f} mm",
            "Status": status
        })

    st.dataframe(pd.DataFrame(preload_data), hide_index=True)

    st.info("""
    **Disclaimers:**
    * **Rate Tolerance:** Standard coils vary +/- 5%.
    * **Stroke Compatibility:** Ensure spring stroke > shock stroke.
    * **Diameter:** Check spring ID compatibility.
    """)
else:
    st.error("Please ensure Stroke and Travel are set greater than 0.")
