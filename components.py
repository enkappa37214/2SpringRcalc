# components.py
import streamlit as st
from constants import CATEGORY_DATA, SKILL_MODIFIERS

def reset_form_callback():
    """Clears all session state variables."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]

def update_bias_from_category():
    """Syncs rear bias slider with the selected bike category."""
    if 'category_select' in st.session_state:
        cat = st.session_state.category_select
        st.session_state.rear_bias_slider = CATEGORY_DATA[cat]["bias"]

def update_category_from_bike():
    """Determines category based on travel when a database bike is selected."""
    from logic import load_bike_database  # Local import prevents circular dependency
    
    selected_model = st.session_state.bike_selector
    bike_db = load_bike_database()
    
    if selected_model and not bike_db.empty:
        bike_row = bike_db[bike_db['Model'] == selected_model].iloc[0]
        t = bike_row['Travel_mm']
        cat_keys = list(CATEGORY_DATA.keys())
        
        # Categorisation logic derived from travel brackets
        if t < 125: 
            cat_name = cat_keys[0]    # Downcountry
        elif t < 140: 
            cat_name = cat_keys[1]  # Trail
        elif t < 155: 
            cat_name = cat_keys[2]  # All-Mountain
        elif t < 170: 
            cat_name = cat_keys[3]  # Enduro
        elif t < 185: 
            cat_name = cat_keys[4]  # Long Travel Enduro
        else: 
            cat_name = cat_keys[6]  # Downhill
        
        st.session_state.category_select = cat_name
        st.session_state.rear_bias_slider = CATEGORY_DATA[cat_name]["bias"]

def kinematic_info_block(travel_mm, stroke_mm, progression, category):
    """Renders a static summary of kinematics for Basic Mode."""
    st.markdown(f"""
    **Kinematic Summary (Basic Mode):**
    * System Leverage Ratio: ${travel_mm/stroke_mm:.2f}:1$ (derived from ${travel_mm:.0f}mm \div {stroke_mm:.1f}mm$).
    * Assumed Progression: ${progression}\%$ (standard for {category} category).
    """)

def fine_tuning_table(rear_load_lbs, effective_lr, final_rate, stroke_mm, MM_TO_IN):
    """Generates and displays the preload adjustment data table."""
    st.subheader(f"Fine Tuning (Preload - {final_rate} lbs spring)")
    preload_data = []
    for turns in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        sag_val_calc = (rear_load_lbs * effective_lr / final_rate) - (turns * 1.0 * MM_TO_IN)
        sag_pct = (sag_val_calc / (stroke_mm * MM_TO_IN)) * 100
        preload_data.append({
            "Turns": turns, 
            "Sag (%)": f"{sag_pct:.1f}%", 
            "Status": "OK" if 1.0 <= turns < 3.0 else "Caution"
        })
    st.dataframe(preload_data, hide_index=True)
