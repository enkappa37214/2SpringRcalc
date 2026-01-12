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
    for key in list(st.session_state.keys()):
        del st.session_state[key]

if 'category_select' not in st.session_state:
    st.session_state.category_select = "Enduro"

# --- Constants ---
LB_TO_KG, KG_TO_LB = 0.453592, 2.20462
IN_TO_MM, MM_TO_IN = 25.4, 1/25.4
STONE_TO_KG = 6.35029
PROGRESSIVE_CORRECTION_FACTOR = 0.97
EBIKE_WEIGHT_PENALTY_KG = 8.5
# Patch: Ensure common strokes are floats
COMMON_STROKES = [45.0, 50.0, 52.5, 55.0, 57.5, 60.0, 62.5, 65.0, 70.0, 75.0]

CATEGORY_DATA = {
    "Downcountry": {"travel": 115, "stroke": 45.0, "base_sag": 28.0, "progression": 15.0, "lr_start": 2.82, "desc": "110–120 mm", "bike_mass_def_kg": 12.0, "bias": 60.0},
    "Trail": {"travel": 130, "stroke": 50.0, "base_sag": 30.0, "progression": 19.0, "lr_start": 2.90, "desc": "120–140 mm", "bike_mass_def_kg": 13.5, "bias": 63.0},
    "All-Mountain": {"travel": 145, "stroke": 55.0, "base_sag": 31.0, "progression": 21.0, "lr_start": 2.92, "desc": "140–150 mm", "bike_mass_def_kg": 14.5, "bias": 65.0},
    "Enduro": {"travel": 160, "stroke": 60.0, "base_sag": 33.0, "progression": 23.0, "lr_start": 3.02, "desc": "150–170 mm", "bike_mass_def_kg": 15.10, "bias": 67.0},
    "Long Travel Enduro": {"travel": 175, "stroke": 65.0, "base_sag": 34.0, "progression": 27.0, "lr_start": 3.16, "desc": "170–180 mm", "bike_mass_def_kg": 16.5, "bias": 69.0},
    "Enduro (Race focus)": {"travel": 165, "stroke": 62.5, "base_sag": 32.0, "progression": 26.0, "lr_start": 3.13, "desc": "160–170 mm", "bike_mass_def_kg": 15.8, "bias": 68.0},
    "Downhill (DH)": {"travel": 200, "stroke": 72.5, "base_sag": 35.0, "progression": 28.0, "lr_start": 3.28, "desc": "180–210 mm", "bike_mass_def_kg": 17.5, "bias": 72.0}
}

# Patch: Normalized keys for safety
SKILL_MODIFIERS = {
    "just_starting": {"bias": 4.0}, 
    "beginner": {"bias": 2.0}, 
    "intermediate": {"bias": 0.0}, 
    "advanced": {"bias": -1.0}, 
    "racer": {"bias": -2.0}
}
SKILL_LEVELS = ["Just starting", "Beginner", "Intermediate", "Advanced", "Racer"]

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

PROGRESSIVE_SPRING_DATA = [
    {"model": "350+", "start": 350, "end": 450, "prog": 28},
    {"model": "400+", "start": 400, "end": 520, "prog": 30},
    {"model": "450+", "start": 450, "end": 590, "prog": 31},
    {"model": "500+", "start": 500, "end": 655, "prog": 31},
    {"model": "550+", "start": 550, "end": 720, "prog": 31},
    {"model": "600+", "start": 600, "end": 780, "prog": 30}
]

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
        st.session_state.rear_bias_slider = float(CATEGORY_DATA[cat]["bias"])

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
        st.session_state.rear_bias_slider = float(CATEGORY_DATA[cat_name]["bias"])

# ==========================================================
# 3. UI MAIN
# ==========================================================
col_title, col_reset = st.columns([0.8, 0.2])
with col_title:
    st.title("MTB Spring Rate Calculator")
with col_reset:
    if st.button("Reset", on_click=reset_form_callback, type="secondary", use_container_width=True):
        st.rerun()

st.caption("Capability Notice: This tool was built for personal use. If you think you're smarter, do your own calculator.")

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
with col_r1: 
    skill = st.selectbox("Rider Skill", SKILL_LEVELS, index=2)
    # Patch: Normalized lookup to prevent crashes
    skill_key = skill.lower().replace(" ", "_")
    skill_bias = SKILL_MODIFIERS.get(skill_key, {"bias": 0})["bias"]

with col_r2:
    if unit_mass == "UK Hybrid (st & kg)":
        stone = st.number_input("Rider Weight (st)", 5.0, 20.0, 11.0, 0.5)
        lbs_rem = st.number_input("Rider Weight (+lbs)", 0.0, 13.9, 0.0, 1.0)
        rider_kg = (stone * STONE_TO_KG) + (lbs_rem * LB_TO_KG)
    elif unit_mass == "North America (lbs)":
        rider_in = st.number_input("Rider Weight (lbs)", 90.0, 280.0, 160.0, 1.0)
        rider_kg = rider_in * LB_TO_KG
    else:
        rider_kg = st.number_input("Rider Weight (kg)", 40.0, 130.0, 68.0, 0.5)
    
    # Patch: Float cast for Streamlit consistency
    gear_def = 5.0 if unit_mass == "North America (lbs)" else 4.0
    gear_input = st.number_input(f"Gear Weight ({u_mass_label})", 0.0, 25.0, float(gear_def), 0.5)
    gear_kg = gear_input * LB_TO_KG if unit_mass == "North America (lbs)" else gear_input

# --- CHASSIS DATA ---
st.header("2. Chassis Data")

config_col1, config_col2 = st.columns(2)
with config_col1:
    chassis_type = st.radio("Chassis Configuration", ["Analog Bike", "E-Bike"], horizontal=True)
    is_ebike = (chassis_type == "E-Bike")
with config_col2:
    weight_mode = st.radio("Bike Weight Mode", ["Manual Input", "Estimate"], horizontal=True)

st.divider()

col_search, col_toggle = st.columns([0.7, 0.3])
selected_bike_data, is_db_bike, bike_model_log = None, False, ""

with col_toggle: manual_entry_mode = st.checkbox("Add my bike")

with col_search:
    if not bike_db.empty:
        selected_model = st.selectbox(
            "Select Bike Model", 
            list(bike_db['Model'].unique()), 
            index=None, 
            placeholder="Type to search...", 
            key='bike_selector', 
            on_change=update_category_from_bike
        )
        st.caption("If your bike is not available you can either leave field empty or choose to help enrich the global database by adding details about your bike.")
        if selected_model:
            selected_bike_data, is_db_bike, bike_model_log = bike_db[bike_db['Model'] == selected_model].iloc[0], True, selected_model

if manual_entry_mode:
    st.info("Community Contribution: Global database enrichment.")
    col_new1, col_new2, col_new3 = st.columns(3)
    with col_new1: new_year = st.number_input("Year", 2010, 2026, 2025)
    with col_new2: new_brand = st.text_input("Brand", placeholder="e.g. SANTA CRUZ")
    with col_new3: new_name = st.text_input("Model", placeholder="e.g. NOMAD")
    bike_model_log = f"{new_year} {new_brand.upper()} {new_name.upper()}".strip()

category = st.selectbox(
    "Category", 
    options=list(CATEGORY_DATA.keys()), 
    format_func=lambda x: f"{x} ({CATEGORY_DATA[x]['desc']})",
    key='category_select', 
    on_change=update_bias_from_category
)
defaults = CATEGORY_DATA[category]

st.divider()

col_inputs, col_summary = st.columns(2)

with col_inputs:
    size_options = list(SIZE_WEIGHT_MODS.keys())
    
    if weight_mode == "Estimate":
        f_size = st.selectbox("Size", size_options, index=3, key="shared_f_size") 
        mat = st.selectbox("Frame Material", ["Carbon", "Aluminium"])
        level = st.selectbox("Build Level", ["Entry-Level", "Mid-Level", "High-End"])

        level_map = {"Entry-Level": 0, "Mid-Level": 1, "High-End": 2}
        base_val = BIKE_WEIGHT_EST[category][mat][level_map[level]]
        bike_kg = float(base_val + SIZE_WEIGHT_MODS[f_size] + (EBIKE_WEIGHT_PENALTY_KG if is_ebike else 0.0))
        bike_weight_source = f"Estimate ({mat}/{level})"
        
        bike_display_val = bike_kg if unit_mass != "North America (lbs)" else bike_kg * KG_TO_LB
        st.info(f"**Estimated Bike Weight:** {bike_display_val:.1f} {u_mass_label}")
    else:
        f_size = st.selectbox("Frame Size", size_options, index=3, key="shared_f_size") 
        # Patch: Float Cast
        bike_input = st.number_input(f"Bike Weight ({u_mass_label})", 7.0, 45.0, float(defaults["bike_mass_def_kg"]) + (EBIKE_WEIGHT_PENALTY_KG if is_ebike else 0.0))
        bike_kg = float(bike_input * LB_TO_KG if unit_mass == "North America (lbs)" else bike_input)
        bike_weight_source = "Manual"
        
    st.markdown("---")

    unsprung_default = True if weight_mode == "Estimate" else False
    unsprung_mode = st.toggle("Estimate Unsprung Mass", value=unsprung_default)
    
    if unsprung_mode:
        u_tier = st.selectbox("Wheelset Tier", ["Light", "Standard", "Heavy"], index=1)
        u_casing = st.selectbox("Tyre Casing", ["XC (Lightweight)", "Trail (Standard)", "Enduro (Reinforced)", "DH (Dual-ply)"], index=1)
        u_mat = st.selectbox("Rear Triangle Material", ["Carbon", "Aluminium"], index=1)
        inserts = st.checkbox("Tyre Inserts?")
        
        wheels = {"Light": 1.7, "Standard": 2.3, "Heavy": 3.0}[u_tier]
        casings = {"XC (Lightweight)": 0.7, "Trail (Standard)": 0.95, "Enduro (Reinforced)": 1.25, "DH (Dual-ply)": 1.5}
        tyre_mass = casings[u_casing]
        swingarm_base = 0.4 if u_mat == "Carbon" else 0.7
        size_factor = SIZE_WEIGHT_MODS[f_size] * 0.15 
        
        unsprung_kg = tyre_mass + wheels + (swingarm_base + size_factor) + (0.5 if inserts else 0.0) + (1.5 if is_ebike else 0.0)
        unsprung_source = f"Estimate ({u_tier}/{u_casing}/{u_mat})"
        
        u_display_val = unsprung_kg if unit_mass != "North America (lbs)" else unsprung_kg * KG_TO_LB
        st.info(f"**Estimated Unsprung Mass:** {u_display_val:.2f} {u_mass_label}")
    else:
        # Patch: Float Cast
        unsprung_input = st.number_input(f"Unsprung ({u_mass_label})", 0.0, 25.0, 4.27 + (2.0 if is_ebike else 0.0), 0.1)
        unsprung_kg = float(unsprung_input * LB_TO_KG if unit_mass == "North America (lbs)" else unsprung_input)
        unsprung_source = "Manual"

with col_summary:
    st.subheader("Dynamic Mass Distribution")
    if 'rear_bias_slider' not in st.session_state: 
        st.session_state.rear_bias_slider = float(defaults["bias"])
    
    st.markdown(f"**Category Base:** {defaults['bias']}%")
    st.markdown(f"**Skill Recommendation:** {skill_bias:+d}% ({skill})")
    
    final_bias_calc = st.slider("Rear Bias (%)", 55, 80, key="rear_bias_slider")
    
    total_system_kg = rider_kg + gear_kg + bike_kg
    sprung_mass_kg = total_system_kg - unsprung_kg
    rear_val_kg = (sprung_mass_kg * (final_bias_calc/100)) + (unsprung_kg if final_bias_calc > 0 else 0)
    front_val = total_system_kg - rear_val_kg
    
    st.write("---")
    total_display = total_system_kg if unit_mass != "North America (lbs)" else total_system_kg * KG_TO_LB
    front_display = front_val if unit_mass != "North America (lbs)" else front_val * KG_TO_LB
    rear_display = rear_val_kg if unit_mass != "North America (lbs)" else rear_val_kg * KG_TO_LB
    
    st.metric("Total System Mass", f"{total_display:.1f} {u_mass_label}")
    st.progress(final_bias_calc / 100)
    
    res_sub1, res_sub2 = st.columns(2)
    with res_sub1: st.metric("Front Load", f"{front_display:.1f} {u_mass_label}")
    with res_sub2: st.metric("Rear Load", f"{rear_display:.1f} {u_mass_label}")

        
# --- KINEMATICS ---
st.header("3. Shock & Kinematics")
col_k1, col_k2 = st.columns(2)

if is_db_bike:
    raw_travel, raw_stroke, raw_prog, raw_lr_start = float(selected_bike_data['Travel_mm']), float(selected_bike_data['Shock_Stroke']), float(selected_bike_data['Progression_Pct']), float(selected_bike_data['Start_Leverage'])
else:
    raw_travel, raw_stroke, raw_prog, raw_lr_start = 165.0, 62.5, float(defaults["progression"]), float(defaults["lr_start"])

with col_k1:
    travel_in = st.number_input(f"Rear Travel ({u_len_label})", 0.0, 300.0, float(raw_travel if unit_len == "Millimetres (mm)" else raw_travel * MM_TO_IN), 1.0)
