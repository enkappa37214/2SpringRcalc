# logic.py
import pandas as pd
import streamlit as st
from fpdf import FPDF
import datetime
from constants import PROGRESSIVE_CORRECTION_FACTOR, MM_TO_IN

@st.cache_data
def load_bike_database():
    """Initialises and cleans the suspension database from CSV."""
    try:
        df = pd.read_csv("clean_suspension_database.csv")
        cols = ['Travel_mm', 'Shock_Stroke', 'Start_Leverage', 'End_Leverage', 'Progression_Pct']
        for c in cols:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        return df.sort_values('Model')
    except Exception:
        return pd.DataFrame()

def analyze_spring_compatibility(progression_pct, has_hbo):
    """Evaluates frame kinematics to recommend spring types."""
    analysis = {"Linear": {"status": "", "msg": ""}, "Progressive": {"status": "", "msg": ""}}
    if progression_pct > 25:
        analysis["Linear"]["status"] = "OK Optimal"
        analysis["Linear"]["msg"] = "Matches frame kinematics."
        analysis["Progressive"]["status"] = "Caution Avoid"
        analysis["Progressive"]["msg"] = "Risk of harsh Wall Effect."
    elif 12 <= progression_pct <= 25:
        analysis["Linear"]["status"] = "OK Compatible"
        analysis["Linear"]["msg"] = "Use for a plush coil feel."
        analysis["Progressive"]["status"] = "OK Compatible"
        analysis["Progressive"]["msg"] = "Use for more pop and bottom-out resistance."
        if has_hbo: 
            analysis["Linear"]["msg"] += " (HBO handles bottom-out)."
    else:
        analysis["Linear"]["status"] = "Caution"
        analysis["Linear"]["msg"] = "High risk of bottom-out without strong HBO."
        analysis["Progressive"]["status"] = "OK Optimal"
        analysis["Progressive"]["msg"] = "Essential to compensate for lack of ramp-up."
    return analysis

def calculate_spring_rate(rear_load_lbs, effective_lr, stroke_mm, target_sag, spring_type_sel):
    """Calculates the theoretical spring rate baseline."""
    raw_rate = (rear_load_lbs * effective_lr) / (stroke_mm * (target_sag / 100) * MM_TO_IN) if stroke_mm > 0 else 0
    if spring_type_sel == "Progressive Spring": 
        raw_rate *= PROGRESSIVE_CORRECTION_FACTOR
    return raw_rate

def generate_calculation_pdf(data_summary, alt_rates, spring_type_sel, u_len_label):
    """Constructs a binary PDF report for download."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, "MTB Spring Rate Calculation Report", ln=True, align='C')
    pdf.set_font("Arial", size=11)
    pdf.ln(10)
    
    # Section 1: Summary
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, "1. Calculation Summary", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 8, f"Bike: {data_summary['bike_model']}", ln=True)
    pdf.cell(200, 8, f"Sprung Mass: {data_summary['sprung_mass']:.1f} kg", ln=True)
    pdf.cell(200, 8, f"Calculated Rear Load: {data_summary['rear_load']:.1f} lbs", ln=True)
    pdf.cell(200, 8, f"Mathematical Baseline: {data_summary['raw_rate']} lbs/in", ln=True)
    
    # Section 2: Setup
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, "2. Setup Guide", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 8, f"Spring Type: {spring_type_sel}", ln=True)
    
    # Section 3: Alternatives
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, "3. Alternative Rates", ln=True)
    for r_row in alt_rates:
        pdf.cell(200, 8, f"{r_row['Rate (lbs)']}: {r_row['Resulting Sag']} ({r_row['Feel']})", ln=True)
    
    # Section 4: Disclaimer
    pdf.ln(10)
    pdf.set_font("Arial", 'I', 9)
    pdf.multi_cell(0, 5, "Engineering Disclaimer: Actual requirements may deviate due to damper valving, friction, and dynamic riding loads. Physical verification via sag measurement is mandatory.")
    
    return pdf.output(dest="S").encode("latin-1")
