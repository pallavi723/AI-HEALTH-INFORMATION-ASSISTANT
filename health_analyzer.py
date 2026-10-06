"""Reference ranges, lab value analysis and BMI. General adult ranges only."""

# key: (display name, unit, low, high, regex aliases)
REFERENCE_RANGES = {
    "hemoglobin": ("Hemoglobin", "g/dL", 12.0, 17.5, r"hemoglobin|haemoglobin|hb"),
    "wbc": ("WBC count", "/µL", 4000, 11000, r"wbc|total leucocyte count|total leukocyte count|tlc"),
    "platelets": ("Platelets", "/µL", 150000, 450000, r"platelet count|platelets"),
    "glucose": ("Fasting glucose", "mg/dL", 70, 99, r"fasting (?:blood )?(?:glucose|sugar)|fbs|blood glucose|glucose"),
    "hba1c": ("HbA1c", "%", 4.0, 5.6, r"hba1c|glycated hemoglobin|glycosylated hemoglobin"),
    "cholesterol": ("Total cholesterol", "mg/dL", None, 199, r"total cholesterol|cholesterol total"),
    "ldl": ("LDL cholesterol", "mg/dL", None, 99, r"ldl(?: cholesterol)?"),
    "hdl": ("HDL cholesterol", "mg/dL", 40, None, r"hdl(?: cholesterol)?"),
    "triglycerides": ("Triglycerides", "mg/dL", None, 149, r"triglycerides?"),
    "creatinine": ("Creatinine", "mg/dL", 0.6, 1.3, r"serum creatinine|creatinine"),
    "tsh": ("TSH", "mIU/L", 0.4, 4.0, r"tsh|thyroid stimulating hormone"),
    "vitamin_d": ("Vitamin D", "ng/mL", 30, 100, r"vitamin d(?:3)?(?:, 25-?oh)?|25-?oh vitamin d"),
    "vitamin_b12": ("Vitamin B12", "pg/mL", 200, 900, r"vitamin b-?12|b12"),
    "alt": ("ALT (SGPT)", "U/L", 7, 56, r"alt|sgpt"),
    "ast": ("AST (SGOT)", "U/L", 10, 40, r"ast|sgot"),
}

SEX_OVERRIDES = {
    ("hemoglobin", "Male"): (13.5, 17.5),
    ("hemoglobin", "Female"): (12.0, 15.5),
}

NOTES = {
    ("hemoglobin", "low"): "Low hemoglobin can be linked to anemia (e.g. iron or B12 deficiency).",
    ("glucose", "high"): "Raised fasting glucose may suggest prediabetes/diabetes; needs doctor follow-up.",
    ("hba1c", "high"): "HbA1c of 5.7–6.4% is the prediabetes range; 6.5%+ is in the diabetes range.",
    ("cholesterol", "high"): "High cholesterol raises long-term heart risk; diet and activity help.",
    ("ldl", "high"): "High LDL ('bad') cholesterol raises heart disease risk.",
    ("hdl", "low"): "Low HDL ('good') cholesterol is a heart risk factor.",
    ("triglycerides", "high"): "High triglycerides are linked to diet, alcohol and diabetes.",
    ("tsh", "high"): "High TSH can suggest an underactive thyroid.",
    ("tsh", "low"): "Low TSH can suggest an overactive thyroid.",
    ("vitamin_d", "low"): "Low vitamin D is common; sunlight, diet or supplements may be advised by a doctor.",
    ("vitamin_b12", "low"): "Low B12 can cause tiredness and nerve symptoms.",
    ("creatinine", "high"): "High creatinine may indicate reduced kidney function.",
}


def _normalize(key: str, value: float) -> float:
    """Convert common alternative units (e.g. 7.5 x10^3/µL -> 7500)."""
    if key in ("wbc", "platelets") and value < 1000:
        return value * 1000
    return value


def analyze_values(values: dict[str, float], sex: str = "Not specified") -> list[dict]:
    results = []
    for key, raw in values.items():
        if key not in REFERENCE_RANGES:
            continue
        name, unit, low, high, _ = REFERENCE_RANGES[key]
        low, high = SEX_OVERRIDES.get((key, sex), (low, high))
        value = _normalize(key, raw)
        if low is not None and value < low:
            status = "low"
        elif high is not None and value > high:
            status = "high"
        else:
            status = "normal"
        rng = f"{low if low is not None else '-'} – {high if high is not None else '-'}"
        results.append({
            "Test": name, "Value": round(value, 2), "Unit": unit,
            "Reference range": rng, "Status": status,
            "Note": NOTES.get((key, status), ""),
        })
    return results


def calculate_bmi(weight_kg: float, height_cm: float) -> tuple[float, str] | None:
    if not weight_kg or not height_cm or weight_kg <= 0 or height_cm <= 0:
        return None
    bmi = weight_kg / ((height_cm / 100) ** 2)
    if bmi < 18.5:
        cat = "Underweight"
    elif bmi < 23:       # Asian-Indian cut-offs (WHO Asia-Pacific)
        cat = "Normal"
    elif bmi < 25:
        cat = "Overweight (at risk)"
    elif bmi < 30:
        cat = "Overweight"
    else:
        cat = "Obese"
    return round(bmi, 1), cat