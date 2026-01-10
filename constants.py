# constants.py

# --- Conversion Factors ---
LB_TO_KG, KG_TO_LB = 0.453592, 2.20462
IN_TO_MM, MM_TO_IN = 25.4, 1/25.4
STONE_TO_KG = 6.35029
PROGRESSIVE_CORRECTION_FACTOR = 0.97
EBIKE_WEIGHT_PENALTY_KG = 8.5
COMMON_STROKES = [45.0, 50.0, 55.0, 57.5, 60.0, 62.5, 65.0, 70.0, 75.0]

# --- Category Definitions ---
CATEGORY_DATA = {
    "Downcountry": {"travel": 115, "stroke": 45.0, "base_sag": 28, "progression": 15, "lr_start": 2.82, "desc": "110–120 mm", "bike_mass_def_kg": 12.0, "bias": 60},
    "Trail": {"travel": 130, "stroke": 50.0, "base_sag": 30, "progression": 19, "lr_start": 2.90, "desc": "120–140 mm", "bike_mass_def_kg": 13.5, "bias": 63},
    "All-Mountain": {"travel": 145, "stroke": 55.0, "base_sag": 31, "progression": 21, "lr_start": 2.92, "desc": "140–150 mm", "bike_mass_def_kg": 14.5, "bias": 65},
    "Enduro": {"travel": 160, "stroke": 60.0, "base_sag": 33, "progression": 23, "lr_start": 3.02, "desc": "150–170 mm", "bike_mass_def_kg": 15.10, "bias": 67},
    "Long Travel Enduro": {"travel": 175, "stroke": 65.0, "base_sag": 34, "progression": 27, "lr_start": 3.16, "desc": "170–180 mm", "bike_mass_def_kg": 16.5, "bias": 69},
    "Enduro (Race focus)": {"travel": 165, "stroke": 62.5, "base_sag": 32, "progression": 26, "lr_start": 3.13, "desc": "160–170 mm", "bike_mass_def_kg": 15.8, "bias": 68},
    "Downhill (DH)": {"travel": 200, "stroke": 72.5, "base_sag": 35, "progression": 28, "lr_start": 3.28, "desc": "180–210 mm", "bike_mass_def_kg": 17.5, "bias": 72}
}

# --- Skill and Coupling Modifiers ---
SKILL_MODIFIERS = {
    "Just starting": {"bias": +4}, 
    "Beginner": {"bias": +2}, 
    "Intermediate": {"bias": 0}, 
    "Advanced": {"bias": -1}, 
    "Racer": {"bias": -2}
}
SKILL_LEVELS = list(SKILL_MODIFIERS.keys())

COUPLING_COEFFS = {
    "Downcountry": 0.80, 
    "Trail": 0.75, 
    "All-Mountain": 0.70, 
    "Enduro": 0.72, 
    "Long Travel Enduro": 0.90, 
    "Enduro (Race focus)": 0.78, 
    "Downhill (DH)": 0.95
}

# --- Manufacturer Specific Data ---
SPRINDEX_DATA = {
    "XC/Trail (55mm)": {"max_stroke": 55, "ranges": ["380-430", "430-500", "490-560", "550-610", "610-690", "650-760"]},
    "Enduro (65mm)": {"max_stroke": 65, "ranges": ["340-380", "390-430", "450-500", "500-550", "540-610", "610-700"]},
    "DH (75mm)": {"max_stroke": 75, "ranges": ["290-320", "340-370", "400-440", "450-490", "510-570", "570-630"]}
}
