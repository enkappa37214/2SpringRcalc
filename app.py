import streamlit as st
import pandas as pd
import datetime
import numpy as np
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection

# ==========================================================
# 1. CONFIGURATION & DATA CONSTANTS
# ==========================================================
st.set_page_config(page_title="MTB Spring Rate Calculator", page_icon="⚙️", layout="centered")

def reset_form():
    for key in st.session_state.keys():
        del st.session_state[key]
    st.rerun()

if 'category_select' not in st.session_state:
    st.session_state.category_select = "Enduro"

# --- Constants ---
LB_TO_KG, KG_TO_LB = 0.453592, 2.20462
IN_TO_MM, MM_TO_IN = 25.4, 1/25.4
STONE_TO_KG = 6.35029
PROGRESSIVE_CORRECTION_FACTOR = 0.97
EBIKE_WEIGHT_PENALTY_KG = 8.5

CATEGORY_DATA = {
    "Downcountry": {"travel": 115, "stroke": 45.0, "base_sag": 28, "progression": 15, "lr_start": 2.82, "desc": "110–120 mm", "bike_mass_def_kg": 12.0, "bias": 60},
    "Trail": {"travel": 130, "stroke": 50.0, "base_sag": 30, "progression": 19, "lr_start": 2.90, "desc": "120–140 mm", "bike_mass_def_kg": 13.5, "bias": 63},
    "All-Mountain": {"travel": 145, "stroke": 55.0, "base_sag": 31, "progression": 21, "lr_start": 2.92, "desc": "140–150 mm", "bike_mass_def_kg": 14.5, "bias": 65},
    "Enduro": {"travel": 160, "stroke": 60.0, "base_sag": 33, "progression": 23, "lr_start": 3.02, "desc": "150–170 mm", "bike_mass_def_kg": 15.10, "bias": 67},
    "Long Travel Enduro": {"travel": 175, "stroke": 65.0, "base_sag": 34, "progression": 27, "lr_start": 3.16, "desc": "170–180 mm", "bike_mass_def_kg": 16.5, "bias": 69},
    "Enduro (Race focus)": {"travel": 165, "stroke": 62.5, "base_sag": 32, "progression": 26, "lr_start": 3.13, "desc": "160–170 mm", "bike_mass_def_kg": 15.8, "bias": 68},
    "Downhill (DH)": {"travel": 200, "stroke": 72.5, "base_sag": 35, "progression": 28, "lr_start": 3.28, "desc": "180–210 mm", "bike_mass_def_kg": 17.5, "bias": 72}
}

SKILL_MODIFIERS = {"Just starting": {"bias": +4}, "Beginner": {"bias": +2}, "Intermediate": {"bias": 0}, "Advanced": {"bias": -1}, "Racer": {"bias": -2}}
SKILL_LEVELS = list(SKILL_MODIFIERS.keys())
COUPLING_COEFFS = {"Downcountry": 0.80, "Trail": 0.75, "All-Mountain": 0.70, "Enduro": 0.72, "Long Travel Enduro": 0.90, "Enduro (Race focus)": 0.78, "Downhill (DH)": 0.95}
SIZE_WEIGHT_MODS = {"XS": -0.5, "S": -0.25, "M": 0.0, "L": 0.3, "XL": 0.6, "XXL": 0.95}
BIKE_WEIGHT_EST = {
    "Downcountry": {"Carbon": [12.2, 11.4, 10.4], "Aluminium": [13.8, 13.1, 12.5]},
    "Trail": {"Carbon": [14.1, 13.4, 12.8], "Aluminium": [15.4, 14.7, 14.0]},
    "All-Mountain": {"Carbon": [15.0, 14.2, 13.5], "Aluminium": [16.2, 15.5, 14.8]},
    "Enduro": {"Carbon": [16.2, 15.5, 14.8], "Aluminium": [17.5, 16.6, 15.8]},
    "Long Travel Enduro": {"Carbon": [16.8, 16.0, 15.2], "Aluminium": [18.0, 17.2, 16.5]},
    "Enduro (Race focus)": {"Carbon": [16.0, 15.2, 14.5], "Aluminium": [17.2, 16.3, 15.5]},
    "Downhill (DH)": {"Carbon": [17.8, 17.0, 16.2], "Aluminium": [19.5, 18.5, 17.5]}
}
SPRINDEX_DATA = {
    "XC/Trail (55mm)": {"max_stroke": 55, "ranges": ["380-430", "430-500", "490-560", "550-610", "610-690", "650-760"]},
    "Enduro (65mm)": {"max_stroke": 65, "ranges": ["340-380", "390-430", "450-500", "500-550", "540-610", "610-700"]},
    "DH (75mm)": {"max_stroke": 75, "ranges": ["290-320", "340-370", "400-440", "450-490", "510-570", "570-630"]}
}

# ==========================================================
# 2. HELPER FUNCTIONS
# ==========================================================
@st.cache_data
def load_bike_database():
    try:
        df = pd.read_csv("clean_suspension_database.csv")
        cols = ['Travel_mm', 'Shock_Stroke', 'Start_Leverage', 'End_Leverage', 'Progression_Pct']
        for c in cols:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        return df.sort_values('Model')
    except Exception:
        return pd.DataFrame()

def estimate_unsprung(wheel_tier, frame_mat, has_inserts, is_ebike):
    base = 1.0
    wheels = {"Light": 1.7, "Standard": 2.3, "Heavy": 3.0}[wheel_tier]
    swingarm = 0.4 if frame_mat == "Carbon" else 0.7
    inserts = 0.5 if has_inserts else 0.0
    motor_modifier = 1.5 if is_ebike else 0.0 
    return base + wheels + swingarm + inserts + motor_modifier

def analyze_spring_compatibility(progression_pct, has_hbo):
    analysis = {"Linear": {"status": "", "msg": ""}, "Progressive": {"status": "", "msg": ""}}
    if progression_pct > 25:
        analysis["Linear"]["status"] = "OK Optimal"; analysis["Linear"]["msg"] = "Matches frame kinematics perfectly."
        analysis["Progressive"]["status"] = "Caution Avoid"; analysis["Progressive"]["msg"] = "Risk of harsh 'Wall Effect' at bottom-out."
    elif 12 <= progression_pct <= 25:
        analysis["Linear"]["status"] = "OK Compatible"; analysis["Linear"]["msg"] = "Use for a plush coil feel."
        analysis["Progressive"]["status"] = "OK Compatible"; analysis["Progressive"]["msg"] = "Use for more 'pop' and bottom-out resistance."
        if has_hbo: analysis["Linear"]["msg"] += " (HBO handles bottom-out)."
    else:
        analysis["Linear"]["status"] = "Caution"; analysis["Linear"]["msg"] = "High risk of bottom-out without strong HBO."
        analysis["Progressive"]["status"] = "OK Optimal"; analysis["Progressive"]["msg"] = "Essential to compensate for lack of ramp-up."
    return analysis

def update_bias_from_category():
    if 'category_select' in st.session_state:
        cat = st.session_state.category_select
        st.session_state.rear_bias_slider = CATEGORY_DATA[cat]["bias"]

def update_category_from_bike():
    selected_model = st.session_state.bike_selector
    bike_db = load_bike_database()
    if selected_model and selected_model != "Bike not listed?":
        bike_row = bike_db[bike_db['Model'] == selected_model].iloc[0]
        t = bike_row['Travel_mm']
        cat_keys = list(CATEGORY_DATA.keys())
        if t < 125: cat_name = cat_keys[0]
        elif t < 140: cat_name = cat_keys[1]
        elif t < 155: cat_name = cat_keys[2]
        elif t < 170: cat_name = cat_keys[3]
        elif t < 185: cat_name = cat_keys[4]
        else: cat_name = cat_keys[6]
        st.session_state.category_select = cat_name
        st.session_state.rear_bias_slider = CATEGORY_DATA[cat_name]["bias"]

# ==========================================================
# 3. UI MAIN & CHASSIS
# ==========================================================
col_title, col_reset = st.columns([0.8, 0.2])
with col_title:
    st.title("MTB Spring Rate Calculator")
with col_reset:
    st.button("Reset", on_click=reset_form, type="secondary", use_container_width=True)

st.caption("Capability Notice: This tool was built for personal use. If you think you're smarter, do your own calculator.")

bike_db = load_bike_database()

with st.expander("Settings & Units"):
    col_u1, col_u2 = st.columns(2)
    with col_u1: unit_mass = st.radio("Mass Units", ["Global (kg)", "North America (lbs)", "UK Hybrid (st & kg)"])
    with col_u2: unit_len = st.radio("Length Units", ["Millimetres (mm)", "Inches (\")"])

st.header("1. Rider Profile")
col_r1, col_r2 = st.columns(2)
with col_r1: skill = st.selectbox("Rider Skill", SKILL_LEVELS, index=2)
with col_r2:
    if unit_mass == "UK Hybrid (st & kg)":
        stone, lbs_rem = st.number_input("Rider Weight (st)", 5.0, 20.0, 11.0, 0.5), st.number_input("Rider Weight (+lbs)", 0.0, 13.9, 0.0, 1.0)
        rider_kg = (stone * STONE_TO_KG) + (lbs_rem * LB_TO_KG)
    elif unit_mass == "North America (lbs)":
        rider_in = st.number_input("Rider Weight (lbs)", 90.0, 280.0, 160.0, 1.0)
        rider_kg = rider_in * LB_TO_KG
    else:
        rider_kg = st.number_input("Rider Weight (kg)", 40.0, 130.0, 68.0, 0.5)
    gear_def = 5.0 if unit_mass == "North America (lbs)" else 4.0
    gear_kg = st.number_input("Gear Weight (kg)", 0.0, 25.0, gear_def, 0.5)

st.header("2. Chassis Data")
chassis_type = st.radio("Chassis Configuration", ["Analog Bike", "E-Bike"], horizontal=True)
is_ebike = (chassis_type == "E-Bike")

selected_bike_data, is_db_bike, bike_model_log = None, False, ""
col_search, col_toggle = st.columns([0.7, 0.3])
with col_toggle: manual_entry_mode = st.checkbox("Bike not listed?", help="Select to manually add a model to the database.")

with col_search:
    if not manual_entry_mode:
        if not bike_db.empty:
            selected_model = st.selectbox("Select Bike Model (Auto-Fill)", list(bike_db['Model'].unique()), index=None, placeholder="Type to search...", key='bike_selector', on_change=update_category_from_bike)
            if selected_model:
                selected_bike_data, is_db_bike, bike_model_log = bike_db[bike_db['Model'] == selected_model].iloc[0], True, selected_model
                st.success(f"Verified Model Loaded: {selected_model}")
        else: manual_entry_mode = True

if manual_entry_mode:
    st.info("Community Contribution: Enter details below to help enrich the global database.")
    col_new1, col_new2, col_new3 = st.columns(3)
    with col_new1: new_year = st.number_input("Year", 2010, 2026, 2025)
    with col_new2: new_brand = st.text_input("Brand", placeholder="e.g. SANTA CRUZ")
    with col_new3: new_name = st.text_input("Model", placeholder="e.g. NOMAD")
    bike_model_log = f"{new_year} {new_brand.upper()} {new_name.upper()}".strip()
    if not bike_db.empty and bike_model_log in bike_db['Model'].values:
        st.warning(f"Duplicate Detected: '{bike_model_log}' already exists in the database.")

category = st.selectbox("Category", list(CATEGORY_DATA.keys()), format_func=lambda x: f"{x} ({CATEGORY_DATA[x]['desc']})", key='category_select', on_change=update_bias_from_category)
defaults = CATEGORY_DATA[category]

col_c1, col_c2 = st.columns(2)
with col_c1:
    weight_mode = st.radio("Bike Weight Mode", ["Manual Input", "Estimate"], horizontal=True)
    if weight_mode == "Estimate":
        mat, level, size = st.selectbox("Frame Material", ["Carbon", "Aluminium"]), st.selectbox("Build Level", ["Entry-Level", "Mid-Level", "High-End"]), st.selectbox("Size", list(SIZE_WEIGHT_MODS.keys()), index=2)
        bike_kg = BIKE_WEIGHT_EST[category][mat][{"Entry-Level": 0, "Mid-Level": 1, "High-End": 2}[level]] + SIZE_WEIGHT_MODS[size] + (EBIKE_WEIGHT_PENALTY_KG if is_ebike else 0.0)
        frame_size_log = size
    else:
        frame_size_log = st.selectbox("Frame Size", list(SIZE_WEIGHT_MODS.keys()), index=2)
        bike_kg = st.number_input("Bike Weight (kg)", 7.0, 36.0, defaults["bike_mass_def_kg"] + (EBIKE_WEIGHT_PENALTY_KG if is_ebike else 0.0), 0.1)
    
    unsprung_mode = st.toggle("Estimate Unsprung Mass", value=False)
    if unsprung_mode:
        u_tier = st.selectbox("Wheelset Tier", ["Light", "Standard", "Heavy"], index=1)
        u_mat = st.selectbox("Rear Triangle", ["Carbon", "Aluminium"], index=1)
        unsprung_kg = estimate_unsprung(u_tier, u_mat, st.checkbox("Tyre Inserts?"), is_ebike)
    else:
        unsprung_kg = st.number_input("Unsprung (kg)", 0.0, 25.0, 4.27 + (2.0 if is_ebike else 0.0), 0.01)

with col_c2:
    if 'rear_bias_slider' not in st.session_state: st.session_state.rear_bias_slider = defaults["bias"]
    st.markdown("### Rear Bias (%)")
    final_bias_calc = st.slider("Rear Bias (%)", 55, 75, key="rear_bias_slider", label_visibility="collapsed")
    skill_suggestion = SKILL_MODIFIERS[skill]["bias"]
    st.caption(f"Category Default: {defaults['bias']}%")
    if skill_suggestion != 0:
        advice_sign = "+" if skill_suggestion > 0 else ""
        st.info(f"Skill Modifier: {advice_sign}{skill_suggestion}% bias recommended.")
    else:
        st.info("Skill Modifier: 0% bias adjustment recommended.")

# ==========================================================
# 4. KINEMATICS
# ==========================================================
st.header("3. Shock & Kinematics")
col_k1, col_k2 = st.columns(2)

if is_db_bike:
    raw_travel, raw_stroke, raw_prog, raw_lr_start = float(selected_bike_data['Travel_mm']), float(selected_bike_data['Shock_Stroke']), float(selected_bike_data['Progression_Pct']), float(selected_bike_data['Start_Leverage'])
else:
    raw_travel, raw_stroke, raw_prog, raw_lr_start = defaults["travel"], defaults["stroke"], float(defaults["progression"]), float(defaults["lr_start"])

with col_k1:
    travel_mm, stroke_mm = st.number_input("Rear Travel (mm)", 0.0, 300.0, float(raw_travel), 1.0), st.number_input("Shock Stroke (mm)", 1.5, 100.0, float(raw_stroke), 0.5)

with col_k2:
    adv_kinematics = st.checkbox("Advanced Kinematics", value=(is_db_bike or manual_entry_mode))
    if adv_kinematics:
        lr_start, prog_pct = st.number_input("LR Start Rate", 1.5, 4.0, raw_lr_start, 0.05), st.number_input("Progression (%)", -10.0, 60.0, raw_prog, 1.0)
        calc_lr_start = lr_start
    else:
        calc_lr_start, prog_pct = travel_mm / stroke_mm if stroke_mm > 0 else 0, float(defaults["progression"])
        st.caption(f"Calculated Average Leverage Ratio: {calc_lr_start:.2f}")
        st.caption(f"Using category default progression: {prog_pct:.1f}%")

if adv_kinematics and travel_mm > 0:
    st.subheader("Leverage Ratio Curve")
    x_travel = np.linspace(0, travel_mm, 50)
    lr_end = calc_lr_start * (1 - (prog_pct / 100))
    y_lr = np.linspace(calc_lr_start, lr_end, 50)
    chart_data = pd.DataFrame({"Travel (mm)": x_travel, "Leverage Ratio": y_lr}).set_index("Travel (mm)")
    st.line_chart(chart_data)
    st.caption(f"Start: {calc_lr_start:.2f} | End: {lr_end:.2f} | Progression: {prog_pct:.1f}%")

# ==========================================================
# 5. SPRING COMPATIBILITY & SELECTION
# ==========================================================
st.header("4. Spring Compatibility & Selection")

with st.container():
    col_comp, col_sel = st.columns([0.6, 0.4])
    
    with col_comp:
        st.subheader("Analysis")
        # Shock HBO moved here
        has_hbo = st.checkbox("Shock has HBO (Hydraulic Bottom Out)?")
        analysis = analyze_spring_compatibility(progression_pct=prog_pct, has_hbo=has_hbo)
        for s_type, info in analysis.items():
            st.markdown(f"**{info['status']} {s_type}**: {info['msg']}")
            
    with col_sel:
        st.subheader("Selection")
        spring_type = st.selectbox("Select Spring Type", ["Standard Steel (Linear)", "Lightweight Steel/Ti", "Sprindex", "Progressive Coil"])

# ==========================================================
# 6. CALCULATIONS & RESULTS
# ==========================================================
st.header("5. Setup Preferences")
target_sag = st.slider("Target Sag (%)", 20.0, 40.0, float(defaults["base_sag"]), 0.5)

total_drop = (calc_lr_start - (calc_lr_start * (1 - (prog_pct/100))))
effective_lr = calc_lr_start - (total_drop * (target_sag / 100)) if adv_kinematics else travel_mm / stroke_mm
eff_rider_kg = rider_kg + (gear_kg * COUPLING_COEFFS[category])
rear_load_lbs = ((eff_rider_kg + bike_kg) * (final_bias_calc / 100) - unsprung_kg) * KG_TO_LB
raw_rate = (rear_load_lbs * effective_lr) / (stroke_mm * (target_sag / 100) * MM_TO_IN) if stroke_mm > 0 else 0
if spring_type == "Progressive Coil": raw_rate *= PROGRESSIVE_CORRECTION_FACTOR

st.divider()
st.header("Results")
if raw_rate > 0:
    res_c1, res_c2 = st.columns(2)
    res_c1.metric("Calculated spring rate", f"{int(raw_rate)} lbs/in")
    res_c2.metric("Target Sag", f"{target_sag:.1f}% ({stroke_mm * (target_sag / 100):.1f} mm)")

    if spring_type == "Sprindex":
        st.subheader("Sprindex Recommendation")
        family = "XC/Trail (55mm)" if stroke_mm <= 55 else "Enduro (65mm)" if stroke_mm <= 65 else "DH (75mm)"
        st.markdown(f"Recommended Model: {family}")
        for r_str in SPRINDEX_DATA[family]["ranges"]:
            low, high = map(int, r_str.split("-"))
            if low <= raw_rate <= high: st.success(f"Perfect Fit: {r_str} lbs/in")

    st.subheader("Fine Tuning (Preload)")
    final_rate = int(round(raw_rate / 25) * 25)
    preload_data = []
    for turns in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        sag_in = (rear_load_lbs * effective_lr / final_rate) - (turns * 1.0 * MM_TO_IN)
        sag_pct = (sag_in / (stroke_mm * MM_TO_IN)) * 100
        preload_data.append({"Turns": turns, "Sag (%)": f"{sag_pct:.1f}%", "Status": "OK" if 1.0 <= turns < 3.0 else "Caution"})
    st.dataframe(pd.DataFrame(preload_data), hide_index=True)

    def generate_pdf():
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(200, 10, "MTB Spring Rate Calculation Report", ln=True, align='C')
        pdf.set_font("Arial", size=11)
        pdf.ln(10)
        pdf.cell(200, 8, f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}", ln=True)
        pdf.cell(200, 8, f"Bike: {bike_model_log}", ln=True)
        pdf.cell(200, 8, f"Rider Weight: {rider_kg:.1f} kg", ln=True)
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, "Calculation Results", ln=True)
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, f"Recommended Spring Rate: {int(raw_rate)} lbs/in", ln=True)
        pdf.cell(200, 10, f"Target Sag: {target_sag}%", ln=True)
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, f"Preload Fine Tuning ({final_rate} lbs spring)", ln=True)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(60, 8, "Turns", 1); pdf.cell(60, 8, "Resulting Sag (%)", 1); pdf.cell(60, 8, "Status", 1, ln=True)
        pdf.set_font("Arial", size=10)
        for row in preload_data:
            pdf.cell(60, 8, str(row["Turns"]), 1)
            pdf.cell(60, 8, row["Sag (%)"], 1)
            pdf.cell(60, 8, row["Status"], 1, ln=True)
        pdf.ln(10)
        pdf.set_font("Arial", 'I', 9)
        pdf.multi_cell(0, 5, "Engineering Disclaimer: This report provides a theoretical baseline derived from kinematic geometry and static mass properties. Actual spring rate requirements may deviate due to damper valving characteristics, system friction, and dynamic riding loads. Data is for estimation purposes; physical verification via sag measurement is mandatory.")
        return pdf.output(dest="S").encode("latin-1")

    st.download_button(label="Export Results to PDF", data=generate_pdf(), file_name=f"MTB_Spring_Report_{datetime.datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf")

# ==========================================================
# 7. LOGGING & REVIEW
# ==========================================================
st.divider()
st.subheader("Configuration Log")
st.info("Help us improve: By logging your setup, you contribute kinematic data to our global database.")

flat_log = {
    "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "Chassis": chassis_type, "Bike_Model": bike_model_log, "Frame_Size": frame_size_log,
    "Rider_Weight_Kg": round(rider_kg, 1), "Bike_Weight_Kg": round(bike_kg, 1), "Target_Sag_Pct": target_sag,
    "Calculated_Spring_Rate": int(raw_rate) if raw_rate else 0,
    "Kinematics_Source": "Database" if is_db_bike else "User Contributed",
    "Bias_Setting": f"Custom ({final_bias_calc - defaults['bias']:+d}%)",
    "Travel_mm_Log": round(travel_mm, 1), "Stroke_mm_Log": round(stroke_mm, 1),
    "Start_LR_Log": round(calc_lr_start, 2), "Progression_Log": round(prog_pct, 1),
    "Submission_Type": "Verified" if is_db_bike else "User_Contributed"
}

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    if st.button("Save to Google Sheets", type="primary"):
        existing_data = conn.read(worksheet="Sheet1", ttl=5)
        conn.update(worksheet="Sheet1", data=pd.concat([existing_data, pd.DataFrame([flat_log])], ignore_index=True))
        st.success("Setup and Kinematics successfully logged!")
    
    if st.checkbox("Show Submission Review View (Admin Only)"):
        all_logs = conn.read(worksheet="Sheet1", ttl=5)
        st.write("Recent User Contributed Kinematics:")
        st.dataframe(all_logs[all_logs['Submission_Type'] == 'User_Contributed'].tail(10))
except Exception as e: st.error(f"Cloud Connection Inactive: {e}.")

st.markdown("---")
st.subheader("Capability Notice")
st.info(
    """
    **Engineering Disclaimer**
    
    This calculator provides a theoretical baseline derived from kinematic geometry and static mass properties. 
    Actual spring rate requirements may deviate due to:
    * Damper valving characteristics (compression tune).
    * System friction (seals, bushings, bearings).
    * Dynamic riding loads and terrain severity.
    
    Data is provided for estimation purposes; physical verification via sag measurement is mandatory.
    """
)
