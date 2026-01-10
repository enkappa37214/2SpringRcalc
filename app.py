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

# State management for reset functionality
def reset_form_callback():
    for key in st.session_state.keys():
        del st.session_state[key]

if 'category_select' not in st.session_state:
    st.session_state.category_select = "Enduro"

# --- Constants ---
LB_TO_KG, KG_TO_LB = 0.453592, 2.20462
IN_TO_MM, MM_TO_IN = 25.4, 1/25.4
STONE_TO_KG = 6.35029
PROGRESSIVE_CORRECTION_FACTOR = 0.97
EBIKE_WEIGHT_PENALTY_KG = 8.5
COMMON_STROKES = [45.0, 50.0, 55.0, 57.5, 60.0, 62.5, 65.0, 70.0, 75.0]

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

def analyze_spring_compatibility(progression_pct, has_hbo):
    analysis = {"Linear": {"status": "", "msg": ""}, "Progressive": {"status": "", "msg": ""}}
    if progression_pct > 25:
        analysis["Linear"]["status"] = "OK Optimal"; analysis["Linear"]["msg"] = "Matches frame kinematics."
        analysis["Progressive"]["status"] = "Caution Avoid"; analysis["Progressive"]["msg"] = "Risk of harsh Wall Effect."
    elif 12 <= progression_pct <= 25:
        analysis["Linear"]["status"] = "OK Compatible"; analysis["Linear"]["msg"] = "Use for a plush coil feel."
        analysis["Progressive"]["status"] = "OK Compatible"; analysis["Progressive"]["msg"] = "Use for more pop and bottom-out resistance."
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
# 3. UI MAIN
# ==========================================================
col_title, col_reset = st.columns([0.8, 0.2])
with col_title:
    st.title("MTB Spring Rate Calculator")
with col_reset:
    if st.button("Reset", on_click=reset_form_callback, type="secondary", use_container_width=True):
        st.rerun()

st.caption("Built for fun, don't take it to seriously.")

bike_db = load_bike_database()

with st.expander("Settings & Units"):
    col_u1, col_u2 = st.columns(2)
    with col_u1: unit_mass = st.radio("Mass Units", ["Global (kg)", "North America (lbs)", "UK Hybrid (st & kg)"])
    with col_u2: unit_len = st.radio("Length Units", ["Millimetres (mm)", "Inches (\")"])

u_mass_label = "lbs" if unit_mass == "North America (lbs)" else "kg"
u_len_label = "in" if unit_len == "Inches (\")" else "mm"

# --- RIDER PROFILE ---
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
    gear_input = st.number_input(f"Gear Weight ({u_mass_label})", 0.0, 25.0, float(gear_def), 0.5)
    gear_kg = gear_input * LB_TO_KG if unit_mass == "North America (lbs)" else gear_input

# --- CHASSIS DATA ---
st.header("2. Chassis Data")
chassis_type = st.radio("Chassis Configuration", ["Analog Bike", "E-Bike"], horizontal=True)
is_ebike = (chassis_type == "E-Bike")

selected_bike_data, is_db_bike, bike_model_log = None, False, ""
col_search, col_toggle = st.columns([0.7, 0.3])

with col_toggle: manual_entry_mode = st.checkbox("Add my bike")

with col_search:
    if not bike_db.empty:
        selected_model = st.selectbox("Select Bike Model", list(bike_db['Model'].unique()), index=None, placeholder="Type to search...", key='bike_selector', on_change=update_category_from_bike)
        st.caption("If your bike is not available you can either leave field empty or choose to help enrich the global database by adding details about your bike.")
        if selected_model:
            selected_bike_data, is_db_bike, bike_model_log = bike_db[bike_db['Model'] == selected_model].iloc[0], True, selected_model

# Conditional input for bike registration
if manual_entry_mode:
    st.info("Community Contribution: Global database enrichment.")
    col_new1, col_new2, col_new3 = st.columns(3)
    with col_new1: new_year = st.number_input("Year", 2010, 2026, 2025)
    with col_new2: new_brand = st.text_input("Brand", placeholder="e.g. SANTA CRUZ")
    with col_new3: new_name = st.text_input("Model", placeholder="e.g. NOMAD")
    bike_model_log = f"{new_year} {new_brand.upper()} {new_name.upper()}".strip()

category = st.selectbox("Category", list(CATEGORY_DATA.keys()), key='category_select', on_change=update_bias_from_category)
defaults = CATEGORY_DATA[category]

col_c1, col_c2 = st.columns(2)
with col_c1:
    # 1. FIXED BIKE WEIGHT LOGIC WITH FRAME SIZE IN BOTH MODES
    weight_mode = st.radio("Bike Weight Mode", ["Manual Input", "Estimate"], horizontal=True)
    
    if weight_mode == "Estimate":
    # ... Material/Level selectors ...
    f_size = st.selectbox("Size", list(SIZE_WEIGHT_MODS.keys()), index=2)
    bike_kg = float(base + SIZE_WEIGHT_MODS[f_size] + (8.5 if is_ebike else 0.0))
    bike_weight_source = f"Estimate ({mat}/{level})"
    else:
    # MODIFICATION: Added Frame Size to manual mode
    f_size = st.selectbox("Frame Size", list(SIZE_WEIGHT_MODS.keys()), index=2) 
    bike_input = st.number_input(f"Bike Weight ({u_mass_label})", 7.0, 45.0, float(defaults["bike_mass_def_kg"]) + (8.5 if is_ebike else 0.0))
    bike_kg = float(bike_input * LB_TO_KG if unit_mass == "North America (lbs)" else bike_input)
    bike_weight_source = "Manual"
        
    # --- Unsprung Mass Source Logic ---
    unsprung_mode = st.toggle("Estimate Unsprung Mass", value=False)
    if unsprung_mode:
        u_tier = st.selectbox("Wheelset Tier", ["Light", "Standard", "Heavy"], index=1)
        u_mat = st.selectbox("Rear Triangle", ["Carbon", "Aluminium"], index=1)
        inserts = st.checkbox("Tyre Inserts?")
        wheels = {"Light": 1.7, "Standard": 2.3, "Heavy": 3.0}[u_tier]
        swingarm = 0.4 if u_mat == "Carbon" else 0.7
        unsprung_kg = 1.0 + wheels + swingarm + (0.5 if inserts else 0.0) + (1.5 if is_ebike else 0.0)
        st.caption(f"Estimated unsprung: {unsprung_kg:.2f} kg")
    else:
        unsprung_input = st.number_input(f"Unsprung ({u_mass_label})", 0.0, 25.0, 4.27 + (2.0 if is_ebike else 0.0), 0.1)
        unsprung_kg = unsprung_input * LB_TO_KG if unit_mass == "North America (lbs)" else unsprung_input

with col_c2:
    if 'rear_bias_slider' not in st.session_state: st.session_state.rear_bias_slider = defaults["bias"]
    
    st.markdown("### Rear Wheel Bias")
    st.text(f"Category Base Bias: {defaults['bias']}%")
    st.text(f"Skill Adjustment Recommendation: {SKILL_MODIFIERS[skill]['bias']:+d}% ({skill})")
    
    final_bias_calc = st.slider("Rear Bias (%)", 55, 80, key="rear_bias_slider", label_visibility="collapsed")
    total_system_kg = rider_kg + gear_kg + bike_kg
    
    # Unsprung mass correction
    sprung_mass_kg = total_system_kg - unsprung_kg
    rear_val_kg = (sprung_mass_kg * (final_bias_calc/100)) + (unsprung_kg if final_bias_calc > 0 else 0)
    
    st.info(f"Front: {(total_system_kg - rear_val_kg):.1f}{u_mass_label} | Rear: {rear_val_kg:.1f}{u_mass_label}")

# --- KINEMATICS ---
st.header("3. Shock & Kinematics")
col_k1, col_k2 = st.columns(2)

if is_db_bike:
    raw_travel, raw_stroke, raw_prog, raw_lr_start = float(selected_bike_data['Travel_mm']), float(selected_bike_data['Shock_Stroke']), float(selected_bike_data['Progression_Pct']), float(selected_bike_data['Start_Leverage'])
else:
    raw_travel, raw_stroke, raw_prog, raw_lr_start = 165.0, 62.5, float(defaults["progression"]), float(defaults["lr_start"])

with col_k1:
    travel_in = st.number_input(f"Rear Travel ({u_len_label})", 0.0, 300.0, float(raw_travel if unit_len == "Millimetres (mm)" else raw_travel * MM_TO_IN), 1.0)
    
    # Shock stroke selectbox with 62.5mm default
    if unit_len == "Inches (\")":
        stroke_in = st.number_input(f"Shock Stroke ({u_len_label})", 1.5, 5.0, raw_stroke * MM_TO_IN, 0.1, disabled=is_db_bike)
        stroke_mm = stroke_in * IN_TO_MM
    else:
        stroke_mm = st.selectbox(f"Shock Stroke ({u_len_label})", COMMON_STROKES, index=COMMON_STROKES.index(62.5), disabled=is_db_bike)
    
    travel_mm = travel_in * IN_TO_MM if unit_len == "Inches (\")" else travel_in

calc_lr_start = travel_mm / stroke_mm if stroke_mm > 0 else 0

with col_k2:
    adv_kinematics = st.checkbox("Advanced Kinematics", value=is_db_bike)
    
    # Conditional summary for basic mode
    if not adv_kinematics:
        st.container()
        st.markdown(f"""
        **Kinematic Summary (Basic Mode):**
        * System Leverage Ratio: ${travel_mm/stroke_mm:.2f}:1$ (derived from ${travel_mm:.0f}mm \div {stroke_mm:.1f}mm$).
        * Assumed Progression: ${defaults['progression']}\%$ (standard for {category} category).
        """)
        prog_pct = float(defaults["progression"])
    else:
        lr_start = st.number_input("LR Start Rate", 1.5, 4.0, raw_lr_start, 0.05)
        prog_pct = st.number_input("Progression (%)", -10.0, 60.0, raw_prog, 1.0)
        calc_lr_start = lr_start

# --- SPRING SELECTION ---
st.header("4. Spring Compatibility & Selection")
target_sag = st.slider("Target Sag (%)", 20.0, 40.0, float(defaults["base_sag"]), 0.5)

with st.container():
    col_comp, col_sel = st.columns([0.6, 0.4])
    with col_comp:
        st.subheader("Analysis")
        has_hbo = st.checkbox("Shock has HBO?")
        analysis = analyze_spring_compatibility(progression_pct=prog_pct, has_hbo=has_hbo)
        for s_type, info in analysis.items():
            st.markdown(f"**{info['status']} {s_type}**: {info['msg']}")
    with col_sel:
        st.subheader("Selection")
        spring_list = ["Standard Steel (Linear)", "Lightweight Steel/Ti (linear)", "Sprindex (20% end progression)", "Progressive Spring"]
        spring_type_sel = st.selectbox("Select Spring Type", spring_list)

# ==========================================================
# 4. CALCULATIONS
# ==========================================================
total_drop = calc_lr_start * (prog_pct / 100)
effective_lr = calc_lr_start - (total_drop * (target_sag / 100)) if adv_kinematics else travel_mm / stroke_mm
eff_rider_kg = rider_kg + (gear_kg * COUPLING_COEFFS[category])

# Calculation fix for rear load
rear_load_lbs = max(0, (sprung_mass_kg * (final_bias_calc / 100))) * KG_TO_LB
raw_rate = (rear_load_lbs * effective_lr) / (stroke_mm * (target_sag / 100) * MM_TO_IN) if stroke_mm > 0 else 0
if spring_type_sel == "Progressive Spring": raw_rate *= PROGRESSIVE_CORRECTION_FACTOR

# ==========================================================
# 5. RESULTS
# ==========================================================
st.divider()
st.header("Results")

if raw_rate > 0:
    res_c1, res_c2 = st.columns(2)
    res_c1.metric("Calculated spring rate", f"{int(raw_rate)} lbs/in")
    sag_val = stroke_mm * (target_sag / 100)
    sag_display = sag_val if unit_len == "Millimetres (mm)" else sag_val * MM_TO_IN
    res_c2.metric("Target Sag", f"{target_sag:.1f}% ({sag_display:.2f} {u_len_label})")

    final_rate_for_tuning = int(round(raw_rate / 25) * 25)
    alt_rates = []

    if "Sprindex" in spring_type_sel:
        family = "XC/Trail (55mm)" if stroke_mm <= 55 else "Enduro (65mm)" if stroke_mm <= 65 else "DH (75mm)"
        ranges = SPRINDEX_DATA[family]["ranges"]
        found_match, gap_neighbors, chosen_range = False, [], ""
        for i, r_str in enumerate(ranges):
            low, high = map(int, r_str.split("-"))
            if low <= raw_rate <= high:
                st.success(f"Perfect Fit: {r_str} lbs/in")
                chosen_range, final_rate_for_tuning, found_match = r_str, int(round(raw_rate / 5) * 5), True
                break
            if i > 0:
                prev_high = int(ranges[i-1].split("-")[1])
                if prev_high < raw_rate < low:
                    gap_neighbors = [(ranges[i-1], prev_high), (r_str, low)]
        
        if not found_match and gap_neighbors:
            st.warning(f"Calculated rate ({int(raw_rate)} lbs) falls in a gap.")
            gap_choice = st.radio("Choose option:", [f"Option A: {gap_neighbors[0][0]} (Plush)", f"Option B: {gap_neighbors[1][0]} (Supportive)"])
            chosen_range = gap_neighbors[0][0] if "Option A" in gap_choice else gap_neighbors[1][0]
            final_rate_for_tuning = gap_neighbors[0][1] if "Option A" in gap_choice else gap_neighbors[1][1]
        
        st.markdown(f"**Sprindex Model:** {family} ({chosen_range} lbs)")
        step = 5 if family != "DH (75mm)" else 10
        center_sprindex = int(round(final_rate_for_tuning / step) * step)
        for r in [center_sprindex - (2*step), center_sprindex - step, center_sprindex, center_sprindex + step, center_sprindex + (2*step)]:
            if r <= 0: continue
            r_sag_pct = ((rear_load_lbs * effective_lr / r) / (stroke_mm * MM_TO_IN)) * 100
            alt_rates.append({"Rate (lbs)": f"{r} lbs", "Resulting Sag": f"{r_sag_pct:.1f}%", "Feel": "Plush" if r < center_sprindex else "Supportive" if r > center_sprindex else "Target"})
    else:
        # Map shock stroke to standard spring stroke availability
        standard_spring_strokes = [55, 60, 65, 75]
        
        # Find the first standard size that is greater than or equal to the shock stroke
        # Defaults to 75 if stroke exceeds standard options
        required_stroke_mm = next((s for s in standard_spring_strokes if s >= stroke_mm), 75)
        
        if unit_len == "Inches (\")":
            spring_size_display = required_stroke_mm * MM_TO_IN
        else:
            spring_size_display = float(required_stroke_mm)

        st.markdown(f"**Required Spring Size:** {spring_size_display:.2f} {u_len_label} Stroke")
        center_rate = int(round(raw_rate / 25) * 25)
        for r in [center_rate - 50, center_rate - 25, center_rate, center_rate + 25, center_rate + 50]:
            if r <= 0: continue
            r_sag_pct = ((rear_load_lbs * effective_lr / r) / (stroke_mm * MM_TO_IN)) * 100
            alt_rates.append({"Rate (lbs)": f"{r} lbs", "Resulting Sag": f"{r_sag_pct:.1f}%", "Feel": "Plush" if r < center_rate else "Supportive" if r > center_rate else "Target"})
    
    st.table(alt_rates)

    # Preload Guide
    st.subheader(f"Fine Tuning (Preload - {final_rate_for_tuning} lbs spring)")
    preload_data = []
    for turns in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        sag_val_calc = (rear_load_lbs * effective_lr / final_rate_for_tuning) - (turns * 1.0 * MM_TO_IN)
        sag_pct = (sag_val_calc / (stroke_mm * MM_TO_IN)) * 100
        preload_data.append({"Turns": turns, "Sag (%)": f"{sag_pct:.1f}%", "Status": "OK" if 1.0 <= turns < 3.0 else "Caution"})
    st.dataframe(pd.DataFrame(preload_data), hide_index=True)

    def generate_pdf():
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16); pdf.cell(200, 10, "MTB Spring Rate Calculation Report", ln=True, align='C')
        pdf.set_font("Arial", size=11); pdf.ln(10)
        
        pdf.set_font("Arial", 'B', 12); pdf.cell(200, 10, "1. Calculation Summary", ln=True)
        pdf.set_font("Arial", size=10)
        pdf.cell(200, 8, f"Bike: {bike_model_log}", ln=True)
        pdf.cell(200, 8, f"Sprung Mass: {sprung_mass_kg:.1f} kg | Unsprung: {unsprung_kg:.1f} kg", ln=True)
        pdf.cell(200, 8, f"Calculated Rear Load: {rear_load_lbs:.1f} lbs", ln=True)
        pdf.cell(200, 8, f"Mathematical Baseline: {int(raw_rate)} lbs/in", ln=True)
        
        pdf.ln(5); pdf.set_font("Arial", 'B', 12); pdf.cell(200, 10, "2. Setup Guide", ln=True)
        pdf.set_font("Arial", size=10); pdf.cell(200, 8, f"Spring Type: {spring_type_sel}", ln=True)
        if "Sprindex" in spring_type_sel:
            pdf.cell(200, 8, f"Chosen Hardware: {chosen_range} lbs", ln=True)
        else:
            pdf.cell(200, 8, f"Required Size: {spring_size_display:.2f} {u_len_label} Stroke", ln=True)
        
        pdf.ln(5); pdf.set_font("Arial", 'B', 12); pdf.cell(200, 10, "3. Alternative Rates", ln=True)
        for r_row in alt_rates:
            pdf.cell(200, 8, f"{r_row['Rate (lbs)']}: {r_row['Resulting Sag']} ({r_row['Feel']})", ln=True)
        
        pdf.ln(10); pdf.set_font("Arial", 'I', 9)
        pdf.multi_cell(0, 5, "Engineering Disclaimer: Actual requirements may deviate due to damper valving, friction, and dynamic riding loads. Physical verification via sag measurement is mandatory.")
        return pdf.output(dest="S").encode("latin-1")
    
    st.download_button(label="Export Results to PDF", data=generate_pdf(), file_name=f"MTB_Spring_Report_{datetime.datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf")

# --- LOGGING ---
st.divider(); st.subheader("Configuration Log")
st.info("Help us improve: By logging your setup, you contribute kinematic data to our global database.")
flat_log = {
    "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "Chassis": chassis_type,
    "Bike_Model": bike_model_log,
    "Frame_Size": f_size, # Guaranteed by UI logic above
    "Rider_Weight_Kg": round(rider_kg, 1),
    "Bike_Weight_Kg": round(bike_kg, 1),
    "Sprung_Mass_Kg": round(total_system_kg - unsprung_kg, 1),
    "Unsprung_Mass_Kg": round(unsprung_kg, 1),
    "Target_Sag_Pct": target_sag,
    "Calculated_Spring_Rate": int(raw_rate),
    "Kinematics_Source": "Verified DB" if selected_bike_data is not None else "User Contributed",
    "Bike_Weight_Source": bike_weight_source, # Guaranteed by if/else block
    "Unsprung_Mass_Source": unsprung_source,   # Guaranteed by if/else block
    "Bias_Setting": f"{final_bias_calc}%",
    "Travel_mm": round(travel_mm, 1),
    "Stroke_mm": round(stroke_mm, 1),
    "Start_LR_Log": round(calc_lr_start, 2),
    "Progression_Log": round(prog_pct, 1),
    "Submission_Type": "Verified" if is_db_bike else "User_Contributed"
}

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    if st.button("Save to Google Sheets", type="primary"):
        existing_data = conn.read(worksheet="Sheet1", ttl=5)
        conn.update(worksheet="Sheet1", data=pd.concat([existing_data, pd.DataFrame([flat_log])], ignore_index=True))
        st.success("Setup successfully logged!")
except Exception as e: st.error(f"Cloud Connection Inactive: {e}.")

st.markdown("---")
st.subheader("Engineering Disclaimer")

disclaimer_text = """
This calculator provides a theoretical baseline derived from kinematic geometry and static mass properties. 
Physical verification via sag measurement is mandatory.
"""

st.info(disclaimer_text)
