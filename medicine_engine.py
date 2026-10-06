"""Rule-based OTC medicine guidance. Educational only: no doses, no prescriptions.
Every suggestion is filtered against age, conditions, allergies and current medicines."""
import re

# ---- health situations the user can tick -----------------------------------
PREG = "Pregnant or breastfeeding"
LIVER = "Liver disease"
KIDNEY = "Kidney disease"
ULCER = "Stomach ulcer / gastritis"
ASTHMA = "Asthma"
HEART = "Heart disease"
BP = "High blood pressure"
DIABETES = "Diabetes"
BLOOD = "Taking blood thinners"
ANTIDEP = "Taking antidepressants"
AGE65 = "Age 65 or above"

CONDITIONS = [PREG, LIVER, KIDNEY, ULCER, ASTHMA, HEART, BP, DIABETES, BLOOD, ANTIDEP]

BLOOD_THINNER_WORDS = ["warfarin", "clopidogrel", "apixaban", "rivaroxaban", "heparin",
                       "dabigatran", "ecosprin", "aspirin"]
ANTIDEP_WORDS = ["fluoxetine", "sertraline", "escitalopram", "paroxetine", "citalopram",
                 "amitriptyline", "venlafaxine", "duloxetine", "ssri", "maoi"]

# ---- medicines / home care ---------------------------------------------------
MEDICINES = {
    "Paracetamol": {
        "class": "Pain and fever reducer",
        "caution": "Check other products (cold/flu mixes, Dolo, Crocin, Calpol) so you don't "
                   "double up on paracetamol. Avoid alcohol. Never exceed the maximum daily "
                   "limit printed on the label.",
        "avoid_if": [LIVER],
        "allergy_keys": ["paracetamol", "acetaminophen"],
        "overlap_keys": ["paracetamol", "acetaminophen", "crocin", "dolo", "calpol", "combiflam"],
    },
    "Ibuprofen": {
        "class": "NSAID pain, fever and inflammation reducer",
        "caution": "Take with food. If you have fever with severe body ache, rash or bleeding "
                   "signs (possible dengue), do NOT take ibuprofen or aspirin until a doctor "
                   "has checked you.",
        "avoid_if": [PREG, ULCER, KIDNEY, ASTHMA, HEART, BP, BLOOD, AGE65],
        "allergy_keys": ["ibuprofen", "nsaid", "aspirin", "diclofenac", "naproxen", "brufen"],
        "overlap_keys": ["ibuprofen", "brufen", "combiflam", "diclofenac", "naproxen",
                         "aceclofenac", "nimesulide", "aspirin", "voveran"],
    },
    "ORS (oral rehydration salts)": {
        "class": "Rehydration",
        "caution": "Mix exactly as the sachet says, using clean water. Don't add extra sugar "
                   "or salt. Take small, frequent sips if vomiting. With kidney or heart "
                   "disease, ask a doctor first.",
        "avoid_if": [], "allergy_keys": [], "overlap_keys": [],
    },
    "Antacid (aluminium/magnesium hydroxide)": {
        "class": "Acid neutraliser",
        "caution": "Usually taken after meals as per the label. Keep a 2-hour gap from other "
                   "medicines. Heartburn more than twice a week needs a doctor.",
        "avoid_if": [KIDNEY],
        "allergy_keys": ["antacid", "aluminium", "magnesium"],
        "overlap_keys": ["antacid", "digene", "gelusil", "mucaine"],
    },
    "Cetirizine": {
        "class": "Antihistamine for allergy",
        "caution": "Can cause drowsiness: avoid driving and alcohol.",
        "avoid_if": [PREG, KIDNEY],
        "allergy_keys": ["cetirizine", "levocetirizine", "antihistamine", "hydroxyzine"],
        "overlap_keys": ["cetirizine", "levocetirizine", "okacet", "cetzine"],
    },
    "Dextromethorphan (dry cough syrup)": {
        "class": "Cough suppressant",
        "caution": "Only for dry cough, not for cough with phlegm. May cause drowsiness. "
                   "Choose a sugar-free syrup if you have diabetes.",
        "avoid_if": [PREG, ASTHMA, ANTIDEP],
        "allergy_keys": ["dextromethorphan"],
        "overlap_keys": ["dextromethorphan"],
    },
    "Expectorant (ambroxol / guaifenesin)": {
        "class": "Loosens phlegm",
        "caution": "Drink plenty of fluids. Choose a sugar-free syrup if you have diabetes.",
        "avoid_if": [PREG, ULCER],
        "allergy_keys": ["ambroxol", "guaifenesin", "bromhexine"],
        "overlap_keys": ["ambroxol", "guaifenesin", "bromhexine"],
    },
    "Isabgol (psyllium husk)": {
        "class": "Bulk-forming fibre laxative",
        "caution": "Take with a full glass of water and keep a 2-hour gap from other "
                   "medicines. Stop and see a doctor for severe belly pain or if you can't "
                   "pass gas or stool.",
        "avoid_if": [], "allergy_keys": ["psyllium", "isabgol"], "overlap_keys": ["isabgol", "psyllium"],
    },
    "Throat lozenges": {
        "class": "Soothes sore throat",
        "caution": "Prefer sugar-free ones if you have diabetes. Don't rely on them for more "
                   "than a few days.",
        "avoid_if": [], "allergy_keys": [], "overlap_keys": [],
    },
    "Saline nasal drops": {
        "class": "Saltwater nasal rinse (non-drug)",
        "caution": "Use clean, sterile or boiled-and-cooled water if making your own.",
        "avoid_if": [], "allergy_keys": [], "overlap_keys": [],
    },
    "Steam inhalation": {
        "class": "Home care",
        "caution": "Keep a safe distance from hot water to avoid burns; not for small children.",
        "avoid_if": [], "allergy_keys": [], "overlap_keys": [],
    },
    "Honey & warm water": {
        "class": "Home care",
        "caution": "Contains sugar: use only a little if you have diabetes.",
        "avoid_if": [], "allergy_keys": ["honey"], "overlap_keys": [],
    },
    "Rest & fluids": {
        "class": "Home care",
        "caution": "Drink water, soups and juices; sleep well.",
        "avoid_if": [], "allergy_keys": [], "overlap_keys": [],
    },
    "Rest in a quiet, dark room": {
        "class": "Home care",
        "caution": "Stay hydrated; avoid screens and loud noise.",
        "avoid_if": [], "allergy_keys": [], "overlap_keys": [],
    },
    "Warm compress & gentle stretching": {
        "class": "Home care",
        "caution": "Use a warm (not hot) pack for 15-20 minutes; don't put it directly on skin.",
        "avoid_if": [], "allergy_keys": [], "overlap_keys": [],
    },
    "Ginger & small sips": {
        "class": "Home care",
        "caution": "Take small sips of water or ginger tea; avoid oily or spicy food.",
        "avoid_if": [], "allergy_keys": ["ginger"], "overlap_keys": [],
    },
    "Light diet (banana, rice, curd)": {
        "class": "Home care",
        "caution": "Avoid oily, spicy food and raw salads until recovered.",
        "avoid_if": [], "allergy_keys": [], "overlap_keys": [],
    },
    "Small meals & avoid trigger foods": {
        "class": "Home care",
        "caution": "Avoid spicy/oily food, late-night meals, tea/coffee and lying down right after eating.",
        "avoid_if": [], "allergy_keys": [], "overlap_keys": [],
    },
    "Fibre, water & activity": {
        "class": "Home care",
        "caution": "Eat fruits, vegetables and whole grains; drink 2-3 L of water; walk daily.",
        "avoid_if": [], "allergy_keys": [], "overlap_keys": [],
    },
}

# ---- symptoms -----------------------------------------------------------------
SYMPTOMS = {
    "Fever": {
        "keywords": ["fever", "temperature", "chills"],
        "options": ["Paracetamol", "Rest & fluids", "Ibuprofen"],
        "red_flags": [
            "Temperature above 39.4°C (103°F), or fever lasting more than 3 days",
            "Fever with rash, severe headache, stiff neck, confusion or repeated vomiting",
            "Fever with severe body pain, bleeding gums or red spots (possible dengue)",
            "Fever during pregnancy, or with diabetes, heart/kidney disease or low immunity",
        ],
    },
    "Headache": {
        "keywords": ["headache", "head ache", "migraine"],
        "options": ["Paracetamol", "Rest in a quiet, dark room", "Ibuprofen"],
        "red_flags": [
            "Sudden, severe 'worst ever' headache",
            "Headache with vision changes, weakness, confusion, fever with stiff neck",
            "Headache after a head injury",
            "Headaches that keep returning or are getting worse",
        ],
    },
    "Body ache / muscle pain": {
        "keywords": ["body ache", "body pain", "muscle pain", "back pain", "joint pain"],
        "options": ["Paracetamol", "Warm compress & gentle stretching", "Ibuprofen"],
        "red_flags": [
            "Swelling or redness in one leg, or severe injury",
            "Numbness or weakness in a limb",
            "Pain lasting more than a week",
        ],
    },
    "Menstrual cramps": {
        "keywords": ["period pain", "menstrual", "cramps"],
        "options": ["Warm compress & gentle stretching", "Paracetamol", "Ibuprofen"],
        "red_flags": [
            "Unusually heavy bleeding or large clots",
            "Severe pain not relieved by usual measures, or pain with fever",
            "Possibility of pregnancy",
        ],
    },
    "Sore throat": {
        "keywords": ["sore throat", "throat pain", "throat"],
        "options": ["Honey & warm water", "Throat lozenges", "Paracetamol"],
        "red_flags": [
            "Difficulty swallowing, breathing or opening the mouth",
            "Sore throat for more than a week, or with high fever and white patches",
            "Rash along with sore throat",
        ],
    },
    "Runny / blocked nose": {
        "keywords": ["runny nose", "blocked nose", "stuffy nose", "cold", "congestion"],
        "options": ["Saline nasal drops", "Steam inhalation", "Cetirizine"],
        "red_flags": [
            "Symptoms lasting more than 10 days",
            "Facial pain with fever, or thick green discharge with fever",
            "Bloody nasal discharge",
        ],
    },
    "Sneezing / itching (allergy)": {
        "keywords": ["sneezing", "allergy", "itching", "itchy", "hives"],
        "options": ["Cetirizine", "Saline nasal drops"],
        "red_flags": [
            "Swelling of lips, face or throat, wheezing or breathing trouble: EMERGENCY",
            "Widespread hives or rash that keeps spreading",
        ],
    },
    "Cough (dry)": {
        "keywords": ["dry cough", "tickly cough"],
        "options": ["Honey & warm water", "Steam inhalation", "Dextromethorphan (dry cough syrup)"],
        "red_flags": [
            "Cough lasting more than 2-3 weeks",
            "Blood in sputum, breathlessness, wheezing or chest pain",
            "Fever with cough for more than 3 days, night sweats or weight loss",
        ],
    },
    "Cough (with phlegm)": {
        "keywords": ["phlegm", "wet cough", "productive cough", "mucus"],
        "options": ["Steam inhalation", "Rest & fluids", "Expectorant (ambroxol / guaifenesin)"],
        "red_flags": [
            "Cough lasting more than 2-3 weeks",
            "Blood in sputum, breathlessness, wheezing or chest pain",
            "Fever with cough for more than 3 days, night sweats or weight loss",
        ],
    },
    "Acidity / heartburn": {
        "keywords": ["acidity", "heartburn", "acid reflux", "gas", "indigestion"],
        "options": ["Small meals & avoid trigger foods", "Antacid (aluminium/magnesium hydroxide)"],
        "red_flags": [
            "Black stools or vomiting blood",
            "Trouble swallowing or unintended weight loss",
            "Chest pain or pain spreading to arm/jaw (could be the heart): EMERGENCY",
            "Symptoms for more than 2 weeks",
        ],
    },
    "Diarrhea": {
        "keywords": ["diarrhea", "diarrhoea", "loose motion", "loose stool"],
        "options": ["ORS (oral rehydration salts)", "Light diet (banana, rice, curd)"],
        "red_flags": [
            "Blood or black stools, or high fever",
            "Dehydration: very dry mouth, little urine, dizziness",
            "Severe belly pain, or diarrhea lasting more than 2 days",
            "Diarrhea in infants or elderly people",
        ],
    },
    "Nausea / vomiting": {
        "keywords": ["nausea", "vomiting", "vomit", "nauseous"],
        "options": ["ORS (oral rehydration salts)", "Ginger & small sips"],
        "red_flags": [
            "Vomiting blood or severe belly pain",
            "Unable to keep fluids down for 24 hours",
            "Vomiting after a head injury, or signs of dehydration",
            "Vomiting during pregnancy",
        ],
    },
    "Constipation": {
        "keywords": ["constipation", "hard stool"],
        "options": ["Fibre, water & activity", "Isabgol (psyllium husk)"],
        "red_flags": [
            "Blood in stool or severe belly pain",
            "No stool or gas with vomiting",
            "Sudden change in bowel habits or weight loss",
        ],
    },
}

GENERAL_NOTES = [
    "Always read the label. Dose and maximum daily limit must come from the product label, "
    "your doctor or a pharmacist; this app does not give doses.",
    "Don't combine products that contain the same ingredient (many cold/flu tablets contain paracetamol).",
    "Check the expiry date, and keep medicines away from children.",
    "Antibiotics and prescription-only medicines must only be taken as prescribed by a doctor.",
]


def detect_symptoms(text: str) -> list[str]:
    t = text.lower()
    found = [name for name, d in SYMPTOMS.items() if any(k in t for k in d["keywords"])]
    if re.search(r"\bcough", t) and not any(s.startswith("Cough") for s in found):
        found.append("Cough (dry)")
    return found


def recommend(symptoms: list[str], age: int, conditions: list[str],
              allergies: str = "", current_meds: str = "", days: int = 1) -> dict:
    out = {"age_block": None, "options": [], "excluded": [], "red_flags": [],
           "general": GENERAL_NOTES}
    if age < 12:
        out["age_block"] = ("Self-medication is not advised for children under 12. Please "
                            "consult a paediatrician before giving any medicine.")
        return out

    conds = set(conditions)
    allergy_text = allergies.lower()
    meds_text = current_meds.lower()
    if age >= 65:
        conds.add(AGE65)
    if any(w in meds_text for w in BLOOD_THINNER_WORDS):
        conds.add(BLOOD)
    if any(w in meds_text for w in ANTIDEP_WORDS):
        conds.add(ANTIDEP)

    seen: dict[str, list[str]] = {}
    for s in symptoms:
        spec = SYMPTOMS.get(s)
        if not spec:
            continue
        for name in spec["options"]:
            seen.setdefault(name, []).append(s)
        for flag in spec["red_flags"]:
            if flag not in out["red_flags"]:
                out["red_flags"].append(flag)

    for name, for_symptoms in seen.items():
        med = MEDICINES[name]
        reasons = []
        hit = sorted(conds & set(med["avoid_if"]))
        if hit:
            reasons.append("Not advised with: " + ", ".join(hit))
        if any(k in allergy_text for k in med["allergy_keys"]):
            reasons.append("Matches a drug allergy you listed")
        if any(k in meds_text for k in med["overlap_keys"]):
            reasons.append("You already take a similar medicine (risk of double dosing)")
        if reasons:
            out["excluded"].append({"name": name, "reasons": reasons})
        else:
            out["options"].append({"name": name, "class": med["class"],
                                   "caution": med["caution"], "for": for_symptoms})

    if days >= 3:
        out["red_flags"].insert(0, f"Your symptoms have lasted {days} days. See a doctor "
                                   "if they have not clearly improved by now.")
    if PREG in conds:
        out["red_flags"].insert(0, "You are pregnant/breastfeeding: check with your doctor "
                                   "before taking any medicine, even common ones.")
    return out