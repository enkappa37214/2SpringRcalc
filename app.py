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
COMMON_STROKES = [45.0, 50.0, 55.0, 57.5, 60.0, 62.5, 65.0, 70.0, 75.0]

CATEGORY_DATA = {
    "Downcountry": {"travel": 115, "stroke": 45.0, "base_sag": 28.0, "progression": 15.0, "lr_start": 2.82, "desc": "110–120 mm", "bike_mass_def_kg": 12.0, "bias": 60.0},
    "Trail": {"travel": 130, "stroke": 50.0, "base_sag": 30.0, "progression": 19.0, "lr_start": 2.90, "desc": "120–140 mm", "bike_mass_def_kg": 13.5, "bias": 63.0},
    "All-Mountain": {"travel": 145, "stroke": 55.0, "base_sag": 31.0, "progression": 21.0, "lr_start": 2.92, "desc": "140–150 mm", "bike_mass_def_kg": 14.5, "bias": 65.0},
    "Enduro": {"travel": 160, "stroke": 60.0, "base_sag": 33.0, "progression": 23.0, "lr_start": 3.02, "desc": "150–170 mm", "bike_mass_def_kg": 15.10, "bias": 67.0},
    "Long Travel Enduro": {"travel": 175, "stroke": 65.0, "base_sag": 34.0, "progression": 27.0, "lr_start": 3.16, "desc": "170–180 mm", "bike_mass_def_kg": 16.5, "bias": 69.0},
    "Enduro (Race focus)": {"travel": 165, "stroke": 62.5, "base_sag": 32.0, "progression": 26.0, "lr_start": 3.13, "desc": "160–170 mm", "bike_mass_def_kg": 15.8, "bias": 68.0},
    "Downhill (DH)": {"travel": 200, "stroke": 75.0, "base_sag": 35.0, "progression": 28.0, "lr_start": 3.28, "desc": "180–210 mm", "bike_mass_def_kg": 17.5, "bias": 72.0}
}

SKILL_MODIFIERS = {"Just starting": {"bias": 4.0}, "Beginner": {"bias": 2.0}, "Intermediate": {"bias": 0.0}, "Advanced": {"bias": -1.0}, "Racer": {"bias": -2.0}}
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
        for c in ['Travel_mm', 'Shock_Stroke', 'Start_Leverage', 'End_Leverage', 'Progression_Pct']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        return df.sort_values('Model')
    except Exception: return pd.DataFrame()

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
        analysis["Linear"]["status"] = "Caution"; analysis["Linear"]["msg"] = "High bottom-out risk."
        analysis["Progressive"]["status"] = "OK Optimal"; analysis["Progressive"]["msg"] = "Essential for lack of ramp-up."
    return analysis

def update_bias_from_category():
    if 'category_select' in st.session_state:
        cat = st.session_state.category_select
        st.session_state.rear_bias_slider = CATEGORY_DATA[cat]["bias"]

def update_category_from_bike():
    selected_model = st.session_state.bike_selector
    bike_db = load_bike_database()
    if selected_model and selected_model != "Bike not listed?":
        st.session_state.category_select = "Enduro" # Manual categorization fallback
        st.session_state.rear_bias_slider = float(CATEGORY_DATA["Enduro"]["bias"])

# ==========================================================
# 3. UI MAIN
# ==========================================================
col_title, col_reset = st.columns([0.8, 0.2])
with col_title: st.title("MTB Spring Rate Calculator")
with col_reset:
    if st.button("Reset", on_click=reset_form_callback, type="secondary", use_container_width=True): st.rerun()

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
        stone = st.number_input("Rider Weight (st)", 5.0, 20.0, 11.0, 0.5)
        lbs_rem = st.number_input("Rider Weight (+lbs)", 0.0, 13.9, 0.0, 1.0)
        rider_kg = (stone * STONE_TO_KG) + (lbs_rem * LB_TO_KG)
    elif unit_mass == "North America (lbs)":
        rider_in = st.number_input("Rider Weight (lbs)", 90.0, 280.0, 160.0, 1.0)
        rider_kg = float(rider_in * LB_TO_KG)
    else:
        rider_kg = float(st.number_input("Rider Weight (kg)", 40.0, 130.0, 68.0, 0.5))
    
    gear_def = 5.0 if unit_mass == "North America (lbs)" else 4.0
    gear_input = st.number_input(f"Gear Weight ({u_mass_label})", 0.0, 25.0, float(gear_def), 0.5)
    gear_kg = float(gear_input * LB_TO_KG if unit_mass == "North America (lbs)" else gear_input)

# --- CHASSIS DATA ---
st.header("2. Chassis Data")
chassis_type = st.radio("Chassis Configuration", ["Analog Bike", "E-Bike"], horizontal=True)
is_ebike = (chassis_type == "E-Bike")

bike_db = load_bike_database()
col_search, col_toggle = st.columns([0.7, 0.3])
with col_toggle: manual_entry_mode = st.checkbox("Add my bike")
with col_search:
    selected_bike_data, bike_model_log = None, "Custom Chassis"
    if not manual_entry_mode and not bike_db.empty:
        selected_model = st.selectbox("Select Bike Model", list(bike_db['Model'].unique()), index=None, placeholder="Search Database...", key='bike_selector', on_change=update_category_from_bike)
        if selected_model:
            selected_bike_data = bike_db[bike_db['Model'] == selected_model].iloc[0]
            bike_model_log = selected_model

category = st.selectbox("Category", list(CATEGORY_DATA.keys()), format_func=lambda x: f"{x} ({CATEGORY_DATA[x]['desc']})", key='category_select', on_change=update_bias_from_category)
defaults = CATEGORY_DATA[category]

col_c1, col_c2 = st.columns(2)
with col_c1:
    bike_input = st.number_input(f"Bike Weight ({u_mass_label})", 7.0, 45.0, float(defaults["bike_mass_def_kg"]) + (EBIKE_WEIGHT_PENALTY_KG if is_ebike else 0.0), 0.5)
    bike_kg = float(bike_input * LB_TO_KG if unit_mass == "North America (lbs)" else bike_input)
    unsprung_input = st.number_input(f"Unsprung Weight ({u_mass_label})", 0.0, 25.0, 4.27 + (2.0 if is_ebike else 0.0), 0.5)
    unsprung_kg = float(unsprung_input * LB_TO_KG if unit_mass == "North America (lbs)" else unsprung_input)

with col_c2:
    if 'rear_bias_slider' not in st.session_state: st.session_state.rear_bias_slider = float(defaults["bias"])
    st.markdown("### Rear Wheel Bias")
    final_bias_calc = st.slider("Rear Bias (%)", 55, 80, key="rear_bias_slider", label_visibility="collapsed")
    total_system_kg = rider_kg + gear_kg + bike_kg
    sprung_mass_kg = total_system_kg - unsprung_kg
    rear_val_kg = (sprung_mass_kg * (final_bias_calc/100)) + unsprung_kg
    
    dist_f = (total_system_kg - rear_val_kg) if unit_mass != "North America (lbs)" else (total_system_kg - rear_val_kg) * KG_TO_LB
    dist_r = rear_val_kg if unit_mass != "North America (lbs)" else rear_val_kg * KG_TO_LB
    st.info(f"Front: {dist_f:.1f}{u_mass_label} | Rear: {dist_r:.1f}{u_mass_label}")

# --- KINEMATICS ---
st.header("3. Shock & Kinematics")
col_k1, col_k2 = st.columns(2)
raw_stroke = float(selected_bike_data['Shock_Stroke']) if selected_bike_data is not None else 62.5
raw_prog = float(selected_bike_data['Progression_Pct']) if selected_bike_data is not None else float(defaults["progression"])

with col_k1:
    if unit_len == "Inches (\")":
        stroke_in = st.number_input(f"Shock Stroke ({u_len_label})", 1.5, 5.0, float(raw_stroke * MM_TO_IN), 0.1)
        stroke_mm = float(stroke_in * IN_TO_MM)
    else:
        stroke_mm = float(st.selectbox(f"Shock Stroke ({u_len_label})", COMMON_STROKES, index=COMMON_STROKES.index(raw_stroke) if raw_stroke in COMMON_STROKES else 4))
    travel_in = st.number_input(f"Rear Travel ({u_len_label})", 0.0, 300.0, float(CATEGORY_DATA[category]["travel"] if unit_len == "Millimetres (mm)" else CATEGORY_DATA[category]["travel"] * MM_TO_IN), 1.0)
    travel_mm = float(travel_in * IN_TO_MM if unit_len == "Inches (\")" else travel_in)

with col_k2:
    adv_kinematics = st.checkbox("Advanced Kinematics", value=(selected_bike_data is not None))
    prog_pct = st.number_input("Frame Progression (%)", 0.0, 60.0, float(raw_prog), 1.0)
    lr_start_val = float(selected_bike_data['Start_Leverage']) if selected_bike_data is not None else float(defaults["lr_start"])
    calc_lr_start = st.number_input("LR Start Rate", 1.5, 4.0, lr_start_val, 0.05) if adv_kinematics else (travel_mm / stroke_mm)

# --- SPRING SELECTION ---
st.header("4. Spring Compatibility & Selection")
target_sag = st.slider("Target Sag (%)", 20.0, 40.0, float(defaults["base_sag"]), 0.5)
with st.container():
    col_comp, col_sel = st.columns([0.6, 0.4])
    with col_comp:
        analysis = analyze_spring_compatibility(progression_pct=prog_pct, has_hbo=st.checkbox("Shock has HBO?"))
        for s_type, info in analysis.items(): st.markdown(f"**{info['status']} {s_type}**: {info['msg']}")
    with col_sel:
        spring_type_sel = st.selectbox("Select Spring Type", ["Standard Steel (Linear)", "Lightweight Steel/Ti (linear)", "Sprindex (20% end progression)", "Progressive Spring"])

# ==========================================================
# 4. CALCULATIONS
# ==========================================================
total_drop = calc_lr_start * (prog_pct / 100)
effective_lr = calc_lr_start - (total_drop * (target_sag / 100))
eff_rider_kg = rider_kg + (gear_kg * COUPLING_COEFFS[category])
rear_load_lbs = max(0, (sprung_mass_kg * (final_bias_calc / 100))) * KG_TO_LB
raw_rate = (rear_load_lbs * effective_lr) / (stroke_mm * (target_sag / 100) * MM_TO_IN) if stroke_mm > 0 else 0
if spring_type_sel == "Progressive Spring": raw_rate *= PROGRESSIVE_CORRECTION_FACTOR

# ==========================================================
# 5. RESULTS
# ==========================================================
st.divider(); st.header("Results")
if raw_rate > 0:
    res_c1, res_c2 = st.columns(2)
    res_c1.metric("Calculated Spring Rate", f"{int(raw_rate)} lbs/in")
    res_sag = (stroke_mm * target_sag/100) if unit_len == "Millimetres (mm)" else (stroke_mm * target_sag/100 * MM_TO_IN)
    res_c2.metric("Target Sag", f"{target_sag:.1f}% ({res_sag:.2f}{u_len_label})")

    final_rate_for_tuning = int(round(raw_rate / 25) * 25)
    alt_rates, chosen_range = [], "N/A"

    if "Sprindex" in spring_type_sel:
        st.subheader("Recommended Spring Model")
        family = "XC/Trail (55mm)" if stroke_mm <= 55 else "Enduro (65mm)" if stroke_mm <= 65 else "DH (75mm)"
        ranges = SPRINDEX_DATA[family]["ranges"]
        found_match = False
        for r_str in ranges:
            low, high = map(int, r_str.split("-"))
            if low <= raw_rate <= high:
                st.success(f"Perfect Fit: {r_str} lbs/in"); chosen_range = r_str
                final_rate_for_tuning, found_match = int(round(raw_rate/5)*5), True; break
        if not found_match:
            gap_choice = st.radio("Rate in gap. Choose:", [f"Plush ({ranges[0]})", f"Supportive ({ranges[-1]})"])
            chosen_range = ranges[0] if "Plush" in gap_choice else ranges[-1]
            final_rate_for_tuning = int(chosen_range.split("-")[1]) if "Plush" in gap_choice else int(chosen_range.split("-")[0])
        st.markdown(f"**Hardware:** {family} ({chosen_range} lbs)")
    else:
        spring_sz = stroke_mm + 5 if unit_len == "Millimetres (mm)" else (stroke_mm * MM_TO_IN) + 0.25
        st.markdown(f"**Spring Type:** {spring_type_sel} | **Required Stroke:** {spring_sz:.2f}{u_len_label}")

    st.markdown("### Comparison of Alternative Settings")
    for r in [final_rate_for_tuning-50, final_rate_for_tuning-25, final_rate_for_tuning, final_rate_for_tuning+25, final_rate_for_tuning+50]:
        if r <= 0: continue
        alt_rates.append({"Rate": f"{r} lbs", "Sag %": f"{((rear_load_lbs * effective_lr / r) / (stroke_mm * MM_TO_IN)) * 100:.1f}%"})
    st.table(alt_rates)

    st.subheader(f"Fine Tuning (Preload - {final_rate_for_tuning} lbs)")
    preload_rows = []
    for t in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        s_pct = (((rear_load_lbs * effective_lr / final_rate_for_tuning) - (t * 1.0 * MM_TO_IN)) / (stroke_mm * MM_TO_IN)) * 100
        preload_rows.append({"Turns": t, "Sag %": f"{s_pct:.1f}%"})
    st.dataframe(pd.DataFrame(preload_rows), hide_index=True)

    def generate_pdf():
        pdf = FPDF()
        pdf.add_page(); pdf.set_font("Arial", 'B', 16); pdf.cell(200, 10, "Spring Rate Report", ln=True, align='C')
        pdf.set_font("Arial", size=10); pdf.ln(5)
        pdf.cell(200, 8, f"Bike: {bike_model_log} | Rate: {int(raw_rate)} lbs/in | Target Sag: {target_sag}%", ln=True)
        pdf.ln(5); pdf.set_font("Arial", 'I', 8)
        pdf.multi_cell(0, 5, "Engineering Disclaimer: Baseline derived from static mass properties. Physical verification via sag measurement is mandatory. Verify Spring ID (35mm/38mm) for compatibility.")
        return pdf.output(dest="S").encode("latin-1")
    st.download_button("Export Results to PDF", data=generate_pdf(), file_name="MTB_Spring_Report.pdf")

st.markdown("---"); st.subheader("Capability Notice")
st.info("Engineering Disclaimer: This calculator provides a theoretical baseline derived from kinematic geometry and static mass properties. Physical verification via sag measurement is mandatory.")
