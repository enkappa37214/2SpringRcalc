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
    for key in list(st.session_state.keys()):
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
    "Downcountry": {"travel": 115, "stroke": 45.0, "base_sag": 28.0, "progression": 15.0, "lr_start": 2.82, "desc": "110–120 mm", "bike_mass_def_kg": 12.0, "bias": 60.0},
    "Trail": {"travel": 130, "stroke": 50.0, "base_sag": 30.0, "progression": 19.0, "lr_start": 2.90, "desc": "120–140 mm", "bike_mass_def_kg": 13.5, "bias": 63.0},
    "All-Mountain": {"travel": 145, "stroke": 55.0, "base_sag": 31.0, "progression": 21.0, "lr_start": 2.92, "desc": "140–150 mm", "bike_mass_def_kg": 14.5, "bias": 65.0},
    "Enduro": {"travel": 160, "stroke": 60.0, "base_sag": 33.0, "progression": 23.0, "lr_start": 3.02, "desc": "150–170 mm", "bike_mass_def_kg": 15.1, "bias": 67.0},
    "Long Travel Enduro": {"travel": 175, "stroke": 65.0, "base_sag": 34.0, "progression": 27.0, "lr_start": 3.16, "desc": "170–180 mm", "bike_mass_def_kg": 16.5, "bias": 69.0},
    "Enduro (Race focus)": {"travel": 165, "stroke": 62.5, "base_sag": 32.0, "progression": 26.0, "lr_start": 3.13, "desc": "160–170 mm", "bike_mass_def_kg": 15.8, "bias": 68.0},
    "Downhill (DH)": {"travel": 200, "stroke": 75.0, "base_sag": 35.0, "progression": 28.0, "lr_start": 3.28, "desc": "180–210 mm", "bike_mass_def_kg": 17.5, "bias": 72.0}
}
SKILL_MODIFIERS = {"just_starting": {"bias": 4.0}, "beginner": {"bias": 2.0}, "intermediate": {"bias": 0.0}, "advanced": {"bias": -1.0}, "racer": {"bias": -2.0}}
SKILL_LABELS = ["Just starting", "Beginner", "Intermediate", "Advanced", "Racer"]
COUPLING_COEFFS = {"Downcountry": 0.80, "Trail": 0.75, "All-Mountain": 0.70, "Enduro": 0.72, "Long Travel Enduro": 0.90, "Enduro (Race focus)": 0.78, "Downhill (DH)": 0.95}
SIZE_WEIGHT_MODS = {"XS": -0.5, "S": -0.25, "M": 0.0, "L": 0.3, "XL": 0.6, "XXL": 0.95}
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
        analysis["Linear"]["status"] = "OK Optimal"; analysis["Linear"]["msg"] = "Matches kinematics."
        analysis["Progressive"]["status"] = "Caution Avoid"; analysis["Progressive"]["msg"] = "Risk of Wall Effect."
    elif 12 <= progression_pct <= 25:
        analysis["Linear"]["status"] = "OK Compatible"; analysis["Linear"]["msg"] = "Plush feel."
        analysis["Progressive"]["status"] = "OK Compatible"; analysis["Progressive"]["msg"] = "More pop."
        if has_hbo: analysis["Linear"]["msg"] += " (HBO handles bottom-out)."
    else:
        analysis["Linear"]["status"] = "Caution"; analysis["Linear"]["msg"] = "Bottom-out risk."
        analysis["Progressive"]["status"] = "OK Optimal"; analysis["Progressive"]["msg"] = "Compensates for low ramp-up."
    return analysis

def update_bias_from_category():
    if 'category_select' in st.session_state:
        cat = st.session_state.category_select
        st.session_state.rear_bias_slider = CATEGORY_DATA[cat]["bias"]

# ==========================================================
# 3. UI MAIN
# ==========================================================
col_title, col_reset = st.columns([0.8, 0.2])
with col_title: st.title("MTB Spring Rate Calculator")
with col_reset: st.button("Reset", on_click=reset_form, type="secondary", use_container_width=True)

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
    skill = st.selectbox("Rider Skill", SKILL_LABELS, index=2)
    skill_key = skill.lower().replace(" ", "_")
    skill_suggestion = SKILL_MODIFIERS.get(skill_key, {"bias": 0.0})
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
    gear_kg = gear_input * LB_TO_KG if unit_mass == "North America (lbs)" else gear_input

# --- CHASSIS DATA ---
st.header("2. Chassis Data")
category = st.selectbox("Category", list(CATEGORY_DATA.keys()), key='category_select', on_change=update_bias_from_category)
defaults = CATEGORY_DATA[category]

col_c1, col_c2 = st.columns(2)
with col_c1:
    bike_input = st.number_input(f"Bike Weight ({u_mass_label})", 7.0, 45.0, float(defaults["bike_mass_def_kg"]), 0.5)
    bike_kg = float(bike_input * LB_TO_KG if unit_mass == "North America (lbs)" else bike_input)
    unsprung_input = st.number_input(f"Unsprung Weight ({u_mass_label})", 0.0, 25.0, 4.27, 0.5)
    unsprung_kg = float(unsprung_input * LB_TO_KG if unit_mass == "North America (lbs)" else unsprung_input)
with col_c2:
    if 'rear_bias_slider' not in st.session_state: st.session_state.rear_bias_slider = defaults["bias"]
    final_bias_calc = st.slider("Rear Bias (%)", 55.0, 80.0, key="rear_bias_slider")
    total_system_kg = rider_kg + gear_kg + bike_kg
    rear_val_kg = total_system_kg * (final_bias_calc / 100)
    st.info(f"Weight Distribution: Front **{(total_system_kg - rear_val_kg):.1f}{u_mass_label}** | Rear **{rear_val_kg:.1f}{u_mass_label}**")

# --- KINEMATICS ---
st.header("3. Setup & Kinematics")
col_k1, col_k2 = st.columns(2)
with col_k1:
    stroke_mm = st.selectbox("Shock Stroke (mm)", [45.0, 50.0, 52.5, 55.0, 57.5, 60.0, 62.5, 65.0, 70.0, 75.0], index=5)
    target_sag = st.slider("Target Sag (%)", 25, 37, int(defaults["base_sag"]))
with col_k2:
    spring_list = ["Standard Steel (Linear)", "Lightweight Steel/Ti (linear)", "Sprindex (20% end progression)", "Progressive Spring"]
    spring_type_sel = st.selectbox("Select Spring Type", spring_list)
    prog_pct = st.number_input("Frame Progression (%)", 0.0, 50.0, float(defaults["progression"]), 1.0)

# ==========================================================
# 4. CALCULATIONS
# ==========================================================
calc_lr_start = float(defaults["lr_start"])
total_drop = calc_lr_start * (prog_pct / 100)
effective_lr = calc_lr_start - (total_drop * (target_sag / 100))
eff_rider_kg = rider_kg + (gear_kg * COUPLING_COEFFS[category])
rear_load_lbs = ((eff_rider_kg + bike_kg) * (final_bias_calc / 100) - unsprung_kg) * KG_TO_LB
raw_rate = (rear_load_lbs * effective_lr) / (stroke_mm * (target_sag / 100) * MM_TO_IN)
if spring_type_sel == "Progressive Spring": raw_rate *= PROGRESSIVE_CORRECTION_FACTOR

# ==========================================================
# 5. RESULTS
# ==========================================================
st.divider()
st.header("Results")
if raw_rate > 0:
    res_c1, res_c2 = st.columns(2)
    res_c1.metric("Calculated Spring Rate", f"{raw_rate:.1f} lbs/in")
    res_c2.metric("Recommended Rate", f"{round(raw_rate / 25) * 25:.0f} lbs/in")
    
    sag_val = float(stroke_mm * (target_sag / 100))
    sag_display = sag_val if unit_len == "Millimetres (mm)" else sag_val * MM_TO_IN
    st.info(f"Target Sag: {target_sag}% ({sag_display:.2f} {u_len_label}) | Required Spring Stroke: {stroke_mm + 5}mm")

    final_rate_for_tuning = int(round(raw_rate / 25) * 25)
    alt_rates = []
    
    # --- SPRING RECOMMENDATION LOGIC ---
    st.subheader(f"Recommended Spring Model")
    if "Sprindex" in spring_type_sel:
        family = "XC/Trail (55mm)" if stroke_mm <= 55 else "Enduro (65mm)" if stroke_mm <= 65 else "DH (75mm)"
        ranges = SPRINDEX_DATA[family]["ranges"]
        found_match, chosen_range = False, "N/A"
        for i, r_str in enumerate(ranges):
            low, high = map(int, r_str.split("-"))
            if low <= raw_rate <= high:
                st.success(f"Perfect Fit: {r_str} lbs/in")
                chosen_range = r_str
                final_rate_for_tuning = int(round(raw_rate / 5) * 5)
                found_match = True; break
        if not found_match:
            st.warning("Rate falls in a hardware gap.")
            gap_choice = st.radio("Option:", [f"Plush ({ranges[0]})", f"Supportive ({ranges[-1]})"])
            final_rate_for_tuning = int(ranges[0].split("-")[1]) if "Plush" in gap_choice else int(ranges[-1].split("-")[0])
            chosen_range = ranges[0] if "Plush" in gap_choice else ranges[-1]
        st.markdown(f"**Sprindex Model:** {family} ({chosen_range} lbs)")
    else:
        st.markdown(f"**Spring Type:** {spring_type_sel}")
        if spring_type_sel == "Progressive Spring":
            st.info(f"Range: {int(raw_rate)} - {int(raw_rate * 1.15)} lbs/in")
        else: st.info(f"Standard Rate: {final_rate_for_tuning} lbs/in")
        
    # --- ALTERNATIVES TABLE ---
    st.markdown("### Comparison of Alternative Spring Rates")
    for r in [final_rate_for_tuning - 50, final_rate_for_tuning - 25, final_rate_for_tuning, final_rate_for_tuning + 25, final_rate_for_tuning + 50]:
        if r <= 0: continue
        r_sag_pct = ((rear_load_lbs * effective_lr / r) / (stroke_mm * MM_TO_IN)) * 100
        alt_rates.append({"Rate (lbs)": f"{r} lbs", "Sag %": f"{r_sag_pct:.1f}%", "Feel": "Plush" if r < final_rate_for_tuning else "Supportive" if r > final_rate_for_tuning else "Target"})
    st.table(alt_rates)

    # --- PRELOAD ---
    st.subheader(f"Fine Tuning (Preload - {final_rate_for_tuning} lbs)")
    preload_data = []
    for turns in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        s_in = (rear_load_lbs * effective_lr / final_rate_for_tuning) - (turns * 1.0 * MM_TO_IN)
        preload_data.append({"Turns": turns, "Sag %": f"{(s_in / (stroke_mm * MM_TO_IN)) * 100:.1f}%", "Status": "OK" if turns < 3.0 else "Caution"})
    st.dataframe(pd.DataFrame(preload_data), hide_index=True)

    # --- PDF EXPORT ---
    def generate_pdf():
        pdf = FPDF()
        pdf.add_page(); pdf.set_font("Arial", 'B', 16); pdf.cell(200, 10, "Spring Rate Report", ln=True, align='C')
        pdf.set_font("Arial", size=10); pdf.ln(10)
        pdf.cell(200, 8, f"Bike: {category} | Calculated Rate: {int(raw_rate)} lbs/in", ln=True)
        pdf.cell(200, 8, f"System Weight: {total_system_kg:.1f} kg | Target Sag: {target_sag}%", ln=True)
        pdf.ln(5); pdf.set_font("Arial", 'B', 12); pdf.cell(200, 10, "Engineering Disclaimer", ln=True); pdf.set_font("Arial", 'I', 8)
        pdf.multi_cell(0, 5, "Theoretical baseline only. Damper valving, friction, and dynamic loads vary. Physical sag verification is mandatory. Verify Spring Internal Diameter (ID) for hardware compatibility.")
        return pdf.output(dest="S").encode("latin-1")
    st.download_button("Export PDF", data=generate_pdf(), file_name="Spring_Report.pdf", mime="application/pdf")

st.divider(); st.subheader("Capability Notice")
st.info("Engineering Disclaimer: Theoretical baseline derived from kinematic geometry and static mass. Physical verification via sag measurement is mandatory. Verify hardware Internal Diameter (ID) to prevent mechanical binding.")
