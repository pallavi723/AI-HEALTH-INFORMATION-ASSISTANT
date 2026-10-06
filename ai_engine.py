"""Gemini wrapper with retries, automatic model fallback, lab extraction and medicine info."""
import json
import re
import time

from google import genai
from google.genai import types

from utils import DISCLAIMER, GEMINI_API_KEY, GEMINI_MODEL, get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = f"""You are an AI Health Information Assistant.
Rules:
- Give clear, accurate, plain-language, EDUCATIONAL health information only.
- Never diagnose, never prescribe medicines. Never give dose numbers: tell the user to follow
  the product label, their doctor's prescription or a pharmacist. Suggest seeing a qualified
  doctor for symptoms that are severe, persistent, worsening, or worrying.
- If CONTEXT is provided, prefer it and mention the source file name. If it does not cover
  the question, say so and answer from general medical knowledge cautiously.
- Use short paragraphs and bullet points. Be empathetic. If unsure, say you are unsure.
- End with: "{DISCLAIMER}"
"""

EXTRACT_SYSTEM = "You extract lab test values from medical report text. Reply with ONLY a JSON object."
LAB_KEYS_PROMPT = """Keys and the units you must convert to:
hemoglobin (g/dL), wbc (/µL, e.g. 7500), platelets (/µL, e.g. 250000), glucose (fasting, mg/dL),
hba1c (%), cholesterol (total, mg/dL), ldl (mg/dL), hdl (mg/dL), triglycerides (mg/dL),
creatinine (mg/dL), tsh (mIU/L), vitamin_d (ng/mL), vitamin_b12 (pg/mL), alt (U/L), ast (U/L).
Only include tests that are present in the text. Values must be plain numbers.
Example: {"hemoglobin": 13.2, "glucose": 98}"""

TRANSIENT = ("429", "500", "502", "503", "504", "UNAVAILABLE",
             "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED", "overloaded", "high demand")
NOT_FOUND = ("NOT_FOUND", "404", "no longer available")
RETRIES_PER_MODEL = 3
MAX_MODELS_TO_TRY = 5


def _strip(name: str) -> str:
    return name.replace("models/", "")


class AIEngine:
    def __init__(self) -> None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL or None
        self._ordered: list[str] | None = None

    # ---- model selection -------------------------------------------------
    def list_models(self) -> list[str]:
        names = []
        for m in self.client.models.list():
            actions = getattr(m, "supported_actions", None) or []
            if "generateContent" in actions:
                names.append(m.name)
        return names

    def _candidates(self) -> list[str]:
        bad = re.compile(r"image|tts|live|embed|audio|robotics|computer|thinking-exp", re.I)
        names = [n for n in self.list_models() if "flash" in n.lower() and not bad.search(n)]

        def score(n: str):
            v = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
            return (float(v.group(1)) if v else 0.0, "lite" not in n, "preview" not in n)

        return sorted(names, key=score, reverse=True)

    def _model_order(self) -> list[str]:
        if self._ordered is not None:
            return self._ordered
        try:
            ordered = self._candidates()
        except Exception as e:
            log.warning("Could not list models: %s", e)
            ordered = []
        if self.model:
            ordered = [self.model] + [n for n in ordered if _strip(n) != _strip(self.model)]
        if not ordered:
            raise RuntimeError("No usable Gemini model found. Check your API key "
                               "and run test_api.py.")
        self._ordered = ordered[:MAX_MODELS_TO_TRY]
        log.info("Model order: %s", self._ordered)
        return self._ordered

    def _pick_model(self) -> str:
        return self._model_order()[0]

    # ---- generation ------------------------------------------------------
    def _generate(self, prompt: str, max_tokens: int = 1500, system: str = SYSTEM_PROMPT,
                  json_mode: bool = False, temperature: float = 0.3) -> str:
        kwargs = dict(system_instruction=system, temperature=temperature,
                      max_output_tokens=max_tokens)
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
        cfg = types.GenerateContentConfig(**kwargs)
        last_err: Exception | None = None

        for model in self._model_order():
            for attempt in range(RETRIES_PER_MODEL):
                try:
                    resp = self.client.models.generate_content(
                        model=model, contents=prompt, config=cfg)
                    text = (resp.text or "").strip()
                    self.model = model
                    return text or "I couldn't generate a response. Please rephrase your question."
                except Exception as e:
                    last_err = e
                    msg = str(e)
                    if any(k in msg for k in NOT_FOUND):
                        log.warning("%s not available, trying next model.", model)
                        break
                    if any(k in msg for k in TRANSIENT):
                        wait = 2 ** attempt
                        log.warning("%s busy (attempt %d/%d), waiting %ds",
                                    model, attempt + 1, RETRIES_PER_MODEL, wait)
                        if attempt < RETRIES_PER_MODEL - 1:
                            time.sleep(wait)
                            continue
                        break
                    raise RuntimeError(f"Gemini request failed: {e}")

        raise RuntimeError("The Gemini service is busy right now. Please wait a minute and "
                           f"try again. (Last error: {last_err})")

    # ---- public API ------------------------------------------------------
    def answer_question(self, question: str, context: list[dict], history: list[dict],
                        profile: str = "") -> str:
        ctx = "\n\n".join(f"[{c['source']}] {c['text']}" for c in context) or "No context found."
        hist = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-6:])
        prompt = (f"USER PROFILE: {profile or 'not provided'}\n\nCONTEXT:\n{ctx}\n\n"
                  f"RECENT CHAT:\n{hist}\n\nQUESTION: {question}")
        return self._generate(prompt)

    def explain_report(self, results: list[dict], profile: str = "") -> str:
        lines = "\n".join(f"- {r['Test']}: {r['Value']} {r['Unit']} "
                          f"(ref {r['Reference range']}) -> {r['Status']}" for r in results)
        prompt = (f"USER PROFILE: {profile or 'not provided'}\n\nLab results:\n{lines}\n\n"
                  "Explain these results in simple language: what each abnormal value may mean, "
                  "general lifestyle/diet tips, and which doctor to consult. Do not diagnose.")
        return self._generate(prompt, max_tokens=2000)

    def extract_values(self, text: str) -> dict[str, float]:
        """Fallback: ask the model to pull lab values out of messy report text."""
        prompt = f"{LAB_KEYS_PROMPT}\n\nREPORT TEXT:\n{text[:12000]}"
        raw = self._generate(prompt, max_tokens=800, system=EXTRACT_SYSTEM,
                             json_mode=True, temperature=0.0)
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        data = json.loads(raw)
        allowed = {"hemoglobin", "wbc", "platelets", "glucose", "hba1c", "cholesterol", "ldl",
                   "hdl", "triglycerides", "creatinine", "tsh", "vitamin_d", "vitamin_b12",
                   "alt", "ast"}
        out = {}
        for k, v in data.items():
            if k in allowed:
                try:
                    out[k] = float(v)
                except (TypeError, ValueError):
                    continue
        return out

    def medicine_guidance(self, symptoms: list[str], options: list[dict], excluded: list[dict],
                          profile: str, days: int) -> str:
        opt = "\n".join(f"- {o['name']} ({o['class']}) for: {', '.join(o['for'])}" for o in options)
        exc = "\n".join(f"- {e['name']}: {'; '.join(e['reasons'])}" for e in excluded) or "none"
        prompt = (
            f"USER PROFILE: {profile}\nSYMPTOMS: {', '.join(symptoms)} (for {days} day(s))\n\n"
            f"SAFE OPTIONS FOUND BY THE APP:\n{opt or 'none'}\n\nNOT SUITABLE FOR THIS USER:\n{exc}\n\n"
            "Task: explain in simple language, ONLY for the listed safe options, why each is "
            "commonly used for these symptoms, common side effects, and safe-use tips. Do NOT "
            "add any other medicine, do NOT give dose numbers (say 'follow the label or ask a "
            "pharmacist'), and briefly explain why the 'not suitable' ones were left out. "
            "Finish with clear signs that mean the user should see a doctor.")
        return self._generate(prompt, max_tokens=1800)

    def medicine_info(self, name: str, profile: str = "") -> str:
        prompt = (
            f"USER PROFILE: {profile or 'not provided'}\n\nGive educational information about "
            f"the medicine: '{name}'. Cover: what it is used for, how it works (simple), common "
            "side effects, serious side effects needing urgent care, who should avoid it, "
            "important interactions (including alcohol and common drugs), and safe-use tips. "
            "Do NOT give dose numbers: say to follow the doctor's prescription or the label. "
            "If you do not recognise the name, say so and suggest checking with a pharmacist.")
        return self._generate(prompt, max_tokens=1800)