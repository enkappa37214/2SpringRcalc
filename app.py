import streamlit as st
import datetime
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# Internal module imports
from constants import *
from logic import *
from components import *

# 1. INITIALISATION
st.set_page_config(page_title="MTB Spring Rate Calculator", page_icon="⚙️", layout="centered")

if 'category_select' not in st.session_state:
    st.session_state.category_select = "Enduro"

# 2. HEADER & RESET
col_title, col_reset = st.columns([0.8, 0.2])
with col_title:
    st.title("MTB Spring Rate Calculator")
with col_reset:
    if st.button("Reset", type="secondary", use_container_width=True):
        reset_form_callback()
        st.rerun()

st.caption("Capability Notice: Built for personal use.")
bike_db = load_bike_database()

# 3. SETTINGS & UNITS
with st.expander("Settings & Units"):
    col_u1, col_u2 = st.columns(2)
    with col_u1: unit_mass = st.radio("Mass Units", ["Global (kg)", "North America (lbs)", "UK Hybrid (st & kg)"])
    with col_u2: unit_len = st.radio("Length Units", ["Millimetres (mm)", "Inches (\")"])

u_mass_label = "lbs" if unit_mass == "North America (lbs)" else "kg"
u_len_label = "in" if unit_len == "Inches (\")" else "mm"

# 4. RIDER PROFILE
st.header("1. Rider Profile")
col_r1, col_r2 = st.columns(2)
with col_r1: 
    skill = st.selectbox("Rider Skill", SKILL_LEVELS, index=2)
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
    
    gear_def = 5.0 if unit_mass == "North America (lbs)" else 4.0
    gear_input = st.number_input(f"Gear Weight ({u_mass_label})", 0.0, 25.0, float(gear_def), 0.5)
    gear_kg = gear_input * LB_TO_KG if unit_mass == "North America (lbs)" else gear_input

# 5. CHASSIS DATA
st.header("2. Chassis Data")
chassis_type = st.radio("Chassis Configuration", ["Analog Bike", "E-Bike"], horizontal=True)
is_ebike = (chassis_type == "E-Bike")

col_search, col_toggle = st.columns([0.7, 0.3])
with col_toggle: 
    manual_entry_mode = st.checkbox("Add my bike")

selected_bike_data, is_db_bike, bike_model_log = None, False, ""
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
            selected_bike_data = bike_db[bike_db['Model'] == selected_model].iloc[0]
            is_db_bike = True
            bike_model_log = selected_model

if manual_entry_mode:
    st.info("Community Contribution: Global database enrichment.")
    col_new1, col_new2, col_new3 = st.columns(3)
    with col_new1: new_year = st.number_input("Year", 2010, 2026, 2025)
    with col_new2: new_brand = st.text_input("Brand", placeholder="e.g. SANTA CRUZ")
    with col_new3: new_name = st.text_input("Model", placeholder="e.g. NOMAD")
    bike_model_log = f"{new_year} {new_brand.upper()} {new_name.upper()}".strip()

category = st.selectbox("Category", list(CATEGORY_DATA.keys()), format_func=lambda x: f"{x} ({CATEGORY_DATA[x]['desc']})", key='category_select', on_change=update_bias_from_category)
defaults = CATEGORY_DATA[category]

# 6. REAR WHEEL BIAS
st.markdown("### Rear Wheel Bias")
col_c1, col_c2 = st.columns(2)
with col_c1:
    bike_input = st.number_input(f"Bike Weight ({u_mass_label})", 7.0, 45.0, defaults["bike_mass_def_kg"] + (EBIKE_WEIGHT_PENALTY_KG if is_ebike else 0.0), 0.1)
    bike_kg = bike_input * LB_TO_KG if unit_mass == "North America (lbs)" else bike_input
    unsprung_kg = (4.27 + (2.0 if is_ebike else 0.0)) * (LB_TO_KG if unit_mass == "North America (lbs)" else 1)

with col_c2:
    if 'rear_bias_slider' not in st.session_state: 
        st.session_state.rear_bias_slider = defaults["bias"]
    
    st.text(f"Category Base Bias: {defaults['bias']}%")
    st.text(f"Skill Adjustment Recommendation: {SKILL_MODIFIERS[skill]['bias']:+d}% ({skill})")
    
    final_bias_calc = st.slider("Rear Bias (%)", 55, 80, key="rear_bias_slider", label_visibility="collapsed")
    total_system_kg = rider_kg + gear_kg + bike_kg
    sprung_mass_kg = total_system_kg - unsprung_kg
    rear_load_lbs = (sprung_mass_kg * (final_bias_calc/100)) * KG_TO_LB
    
    st.info(f"Front: {(total_system_kg*KG_TO_LB if unit_mass=='North America (lbs)' else total_system_kg) - (rear_load_lbs if unit_mass=='North America (lbs)' else rear_load_lbs*LB_TO_KG):.1f}{u_mass_label} | Rear: {(rear_load_lbs if unit_mass=='North America (lbs)' else rear_load_lbs*LB_TO_KG):.1f}{u_mass_label}")

# 7. KINEMATICS
st.header("3. Shock & Kinematics")
if is_db_bike:
    raw_travel, raw_stroke, raw_prog, raw_lr_start = float(selected_bike_data['Travel_mm']), float(selected_bike_data['Shock_Stroke']), float(selected_bike_data['Progression_Pct']), float(selected_bike_data['Start_Leverage'])
else:
    raw_travel, raw_stroke, raw_prog, raw_lr_start = 165.0, 62.5, float(defaults["progression"]), float(defaults["lr_start"])

col_k1, col_k2 = st.columns(2)
with col_k1:
    travel_mm = st.number_input("Rear Travel (mm)", 0.0, 300.0, raw_travel)
    stroke_mm = st.selectbox("Shock Stroke (mm)", COMMON_STROKES, index=COMMON_STROKES.index(62.5), disabled=is_db_bike)

with col_k2:
    adv_kinematics = st.checkbox("Advanced Kinematics", value=is_db_bike)
    if not adv_kinematics:
        kinematic_info_block(travel_mm, stroke_mm, defaults["progression"], category)
        prog_pct, calc_lr_start = float(defaults["progression"]), travel_mm / stroke_mm
    else:
        calc_lr_start = st.number_input("LR Start Rate", 1.5, 4.0, raw_lr_start)
        prog_pct = st.number_input("Progression (%)", -10.0, 60.0, raw_prog)

# 8. RESULTS
st.divider()
st.header("Results")
target_sag = st.slider("Target Sag (%)", 20.0, 40.0, float(defaults["base_sag"]), 0.5)
spring_type_sel = st.selectbox("Select Spring Type", ["Standard Steel (Linear)", "Lightweight Steel/Ti (linear)", "Sprindex (20% end progression)", "Progressive Spring"])

eff_lr = calc_lr_start - ((calc_lr_start * (prog_pct / 100)) * (target_sag / 100))
raw_rate = calculate_spring_rate(rear_load_lbs, eff_lr, stroke_mm, target_sag, spring_type_sel)

if raw_rate > 0:
    res_c1, res_c2 = st.columns(2)
    res_c1.metric("Calculated Spring Rate", f"{int(raw_rate)} lbs/in")
    sag_val = stroke_mm * (target_sag / 100)
    res_c2.metric("Target Sag", f"{target_sag:.1f}% ({sag_val if unit_len=='Millimetres (mm)' else sag_val*MM_TO_IN:.2f} {u_len_label})")

    # Alternative Rates
    alt_rates = []
    center_rate = int(round(raw_rate / 25) * 25)
    for r in [center_rate - 50, center_rate - 25, center_rate, center_rate + 25, center_rate + 50]:
        if r <= 0: continue
        r_sag_pct = ((rear_load_lbs * eff_lr / r) / (stroke_mm * MM_TO_IN)) * 100
        alt_rates.append({"Rate (lbs)": f"{r} lbs", "Resulting Sag": f"{r_sag_pct:.1f}%", "Feel": "Plush" if r < center_rate else "Supportive" if r > center_rate else "Target"})
    st.table(alt_rates)

    # PDF Export
    data_summary = {"bike_model": bike_model_log, "sprung_mass": sprung_mass_kg, "rear_load": rear_load_lbs, "raw_rate": int(raw_rate)}
    pdf_bytes = generate_calculation_pdf(data_summary, alt_rates, spring_type_sel, u_len_label)
    st.download_button(label="Export Results to PDF", data=pdf_bytes, file_name=f"MTB_Report_{datetime.datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf")

# 9. LOGGING
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    if st.button("Save to Google Sheets", type="primary"):
        flat_log = {"Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Bike_Model": bike_model_log, "Spring_Rate": int(raw_rate)}
        existing_data = conn.read(worksheet="Sheet1", ttl=5)
        conn.update(worksheet="Sheet1", data=pd.concat([existing_data, pd.DataFrame([flat_log])], ignore_index=True))
        st.success("Setup successfully logged!")
except Exception as e:
    st.error(f"Cloud Connection Inactive: {e}")

st.divider()
st.info("Engineering Disclaimer: This calculator provides a theoretical baseline. Physical verification via sag measurement is mandatory.")
