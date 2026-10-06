"""Extract text from uploaded reports and pull out lab values."""
import re
from io import BytesIO

from pypdf import PdfReader

from health_analyzer import REFERENCE_RANGES
from utils import clean_text, get_logger

log = get_logger(__name__)

# Extra spellings used by different labs (added to the aliases in health_analyzer.py)
EXTRA_ALIASES = {
    "hemoglobin": r"hemoglobin \(hb\)|haemoglobin \(hb\)|hgb",
    "wbc": r"white blood cell(?:s| count)?|total wbc count|leuc?ocytes?|leukocytes?",
    "platelets": r"platelet|plt",
    "glucose": r"plasma glucose|glucose fasting|glucose \(fasting\)|blood sugar(?: fasting)?|fasting plasma glucose",
    "hba1c": r"glyco(?:sylated|lated) h(?:a)?emoglobin|hb ?a1c|a1c",
    "cholesterol": r"serum cholesterol|cholesterol, total|cholesterol - total|cholesterol-total",
    "ldl": r"ldl-c|ldl-cholesterol|low density lipoprotein",
    "hdl": r"hdl-c|hdl-cholesterol|high density lipoprotein",
    "triglycerides": r"serum triglycerides|tg",
    "creatinine": r"s\. creatinine|serum creat",
    "vitamin_d": r"25 hydroxy vitamin d|vitamin d total|vit(?:amin)? d",
    "vitamin_b12": r"cyanocobalamin|vit(?:amin)? b-?12",
    "alt": r"alanine (?:amino)?transaminase|alanine aminotransferase",
    "ast": r"aspartate (?:amino)?transaminase|aspartate aminotransferase",
}

# Words that must NOT come right before the test name (e.g. glycated HEMOGLOBIN is HbA1c, not Hb)
LOOKBEHIND = {
    "hemoglobin": r"(?<!glycated )(?<!glycosylated )(?<!glycosylated\n)(?<!corpuscular )(?<!glyco-)",
}

# Plausible raw values - rejects wrong numbers such as dates, page numbers, ranges
PLAUSIBLE = {
    "hemoglobin": (3, 25), "wbc": (0.5, 200000), "platelets": (0.5, 2000000),
    "glucose": (20, 800), "hba1c": (3, 20), "cholesterol": (50, 600),
    "ldl": (10, 500), "hdl": (5, 150), "triglycerides": (20, 3000),
    "creatinine": (0.1, 20), "tsh": (0.01, 150), "vitamin_d": (1, 300),
    "vitamin_b12": (50, 3000), "alt": (1, 3000), "ast": (1, 3000),
}

NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"


def extract_text_from_file(data: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise ValueError("This PDF is password protected.")
        pages = []
        for p in reader.pages:
            try:
                pages.append(p.extract_text() or "")
            except Exception as e:  # one bad page should not kill the whole file
                log.warning("Page extraction failed: %s", e)
        text = "\n\n".join(pages)
        if not text.strip():
            raise ValueError("No readable text found - this looks like a scanned image PDF. "
                             "Upload a text-based PDF/TXT, or enter the values manually below.")
        return clean_text(text)
    if name.endswith((".txt", ".md")):
        return clean_text(data.decode("utf-8", errors="ignore"))
    raise ValueError("Unsupported file type. Upload a PDF or TXT file.")


def _prepare(text: str) -> str:
    """Remove unit exponents like 'x10^3/µL' so '10' / '3' are not read as results."""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[x×*]?\s*10\s*(?:\^|\*\*|\*)\s*-?\d+", " ", text, flags=re.I)
    text = re.sub(r"[x×]?\s*10[²³⁴⁵⁶⁷⁸⁹]", " ", text, flags=re.I)
    return text


def _normalize(key: str, value: float) -> float:
    """Convert common alternative units to the units used in health_analyzer."""
    if key == "wbc" and value < 1000:           # 7.5 (x10^3/µL) -> 7500
        return value * 1000
    if key == "platelets":
        if value < 20:                          # 2.5 lakh -> 250000
            return value * 100000
        if value < 1000:                        # 250 (x10^3/µL) -> 250000
            return value * 1000
    return value


def _find(key: str, text: str, multiline: bool) -> float | None:
    aliases = REFERENCE_RANGES[key][4]
    extra = EXTRA_ALIASES.get(key)
    if extra:
        aliases = f"{aliases}|{extra}"
    gap = r"[^\d]" if multiline else r"[^\d\n]"
    # Zero-width lookahead so overlapping candidates (e.g. 'Glycosylated Hemoglobin (HbA1c) 6.1')
    # are all tried and a wrong early match cannot hide the right one.
    pattern = (rf"(?=({LOOKBEHIND.get(key, '')}(?<![A-Za-z])(?:{aliases})(?![A-Za-z])"
               rf"{gap}{{0,40}}?{NUM}))")
    lo, hi = PLAUSIBLE[key]
    for m in re.finditer(pattern, text, flags=re.IGNORECASE):
        try:
            val = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        if lo <= val <= hi:
            return val
    return None


def extract_lab_values(text: str) -> dict[str, float]:
    """Find lab values by name. Tries same-line first, then values on the next line."""
    text = _prepare(text)
    found: dict[str, float] = {}
    for key in REFERENCE_RANGES:
        if key not in PLAUSIBLE:
            continue
        val = _find(key, text, multiline=False)
        if val is None:
            val = _find(key, text, multiline=True)
        if val is not None:
            found[key] = _normalize(key, val)
    return found


def find_lab_values(text: str, ai=None) -> tuple[dict[str, float], str]:
    """Pattern matching first; if few values are found, ask the AI to extract the rest."""
    values = extract_lab_values(text)
    method = "pattern matching"
    if ai is not None and len(values) < 3:
        try:
            ai_vals = ai.extract_values(text)
            added = {}
            for k, v in ai_vals.items():
                lo, hi = PLAUSIBLE.get(k, (None, None))
                if k not in values and lo is not None and lo <= v <= hi:
                    added[k] = v
            if added:
                values.update(added)
                method = "pattern matching + AI"
        except Exception as e:
            log.warning("AI extraction failed: %s", e)
    return values, method