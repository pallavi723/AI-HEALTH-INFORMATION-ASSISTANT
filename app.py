"""AI Health Information Assistant - Streamlit UI.   Run: streamlit run app.py"""
import uuid

import pandas as pd
import streamlit as st

import database as db
from ai_engine import AIEngine
from health_analyzer import REFERENCE_RANGES, analyze_values, calculate_bmi
from medicine_engine import CONDITIONS, SYMPTOMS, detect_symptoms, recommend
from rag_engine import RAGEngine
from report_parser import extract_text_from_file, find_lab_values
from utils import DISCLAIMER, EMERGENCY_MESSAGE, UPLOAD_DIR, is_emergency

st.set_page_config(page_title="AI Health Information Assistant", page_icon="🩺", layout="wide")
db.init_db()


@st.cache_resource(show_spinner="Loading knowledge base...")
def get_rag() -> RAGEngine:
    rag = RAGEngine()
    if rag.count() == 0:
        rag.ingest()
    return rag


@st.cache_resource
def get_ai() -> AIEngine:
    return AIEngine()


if "sid" not in st.session_state:
    st.session_state.sid = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "parsed" not in st.session_state:
    st.session_state.parsed = {}
sid = st.session_state.sid

# ---------------- Sidebar ----------------
with st.sidebar:
    st.title("🩺 Health Assistant")
    st.subheader("Your profile")
    age = st.number_input("Age", 1, 120, 30)
    sex = st.selectbox("Sex", ["Not specified", "Male", "Female"])
    weight = st.number_input("Weight (kg)", 0.0, 300.0, 0.0, step=0.5)
    height = st.number_input("Height (cm)", 0.0, 250.0, 0.0, step=0.5)
    bmi = calculate_bmi(weight, height)
    if bmi:
        st.metric("BMI", bmi[0], bmi[1])
    profile = f"Age {age}, sex {sex}" + (f", BMI {bmi[0]} ({bmi[1]})" if bmi else "")

    st.divider()
    if st.button("🔄 Re-index knowledge base"):
        with st.spinner("Indexing..."):
            n = get_rag().ingest()
        st.success(f"Indexed {n} chunks")
    st.caption(DISCLAIMER)

try:
    ai = get_ai()
    rag = get_rag()
except Exception as e:
    st.error(f"Setup problem: {e}")
    st.stop()

tab_chat, tab_report, tab_med, tab_hist = st.tabs(
    ["💬 Ask a question", "🧪 Analyze lab report", "💊 Medicine guide", "🗂 History"])

# ---------------- Chat ----------------
with tab_chat:
    st.info(DISCLAIMER)
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    q = st.chat_input("Ask about symptoms, nutrition, conditions, medicines...")
    if q:
        st.session_state.messages.append({"role": "user", "content": q})
        db.save_message(sid, "user", q)
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            if is_emergency(q):
                reply = EMERGENCY_MESSAGE
            else:
                with st.spinner("Thinking..."):
                    try:
                        ctx = rag.query(q)
                        reply = ai.answer_question(q, ctx, st.session_state.messages[:-1], profile)
                        if ctx:
                            reply += "\n\n*Sources:* " + ", ".join(sorted({c['source'] for c in ctx}))
                    except Exception as e:
                        reply = f"Sorry, something went wrong: {e}"
            st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
        db.save_message(sid, "assistant", reply)

# ---------------- Report analysis ----------------
with tab_report:
    st.write("Upload a lab report (PDF or TXT with selectable text, not a photo), "
             "or just type the values in manually below.")
    f = st.file_uploader("Report file", type=["pdf", "txt"])

    fkey = "manual"
    info = {"text": "", "values": {}, "method": "", "error": None}
    if f:
        fkey = f"{f.name}_{f.size}"
        if fkey not in st.session_state.parsed:
            data = f.getvalue()
            (UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{f.name}").write_bytes(data)
            try:
                text = extract_text_from_file(data, f.name)
                with st.spinner("Reading report..."):
                    values, method = find_lab_values(text, ai)
                st.session_state.parsed[fkey] = {"text": text, "values": values,
                                                 "method": method, "error": None}
            except Exception as e:
                st.session_state.parsed[fkey] = {"text": "", "values": {}, "method": "",
                                                 "error": str(e)}
        info = st.session_state.parsed[fkey]
        if info["error"]:
            st.error(info["error"])
        else:
            st.caption(f"Detected {len(info['values'])} value(s) using {info['method']}.")
            with st.expander("Show text read from the file"):
                st.text(info["text"][:4000])

    with st.expander("✏️ Add or correct values manually",
                     expanded=bool(f) and not info["values"]):
        st.caption("Enter 0 to skip a test. Use the units shown in brackets.")
        final: dict[str, float] = {}
        cols = st.columns(3)
        for i, (key, spec) in enumerate(REFERENCE_RANGES.items()):
            v = cols[i % 3].number_input(
                f"{spec[0]} ({spec[1]})", min_value=0.0,
                value=float(info["values"].get(key, 0.0)), key=f"man_{fkey}_{key}")
            if v > 0:
                final[key] = v

    results = analyze_values(final, sex)
    if results:
        df = pd.DataFrame(results)
        st.dataframe(df.style.map(
            lambda s: "background-color:#ffd6d6" if s in ("low", "high") else "",
            subset=["Status"]))
        abnormal = [r for r in results if r["Status"] != "normal"]
        st.write(f"**{len(results)}** values analysed, **{len(abnormal)}** outside the reference range.")
        if st.button("🤖 Explain my results"):
            with st.spinner("Analyzing..."):
                try:
                    summary = ai.explain_report(results, profile)
                    st.markdown(summary)
                    db.save_report(sid, f.name if f else "manual entry", results, summary)
                except Exception as e:
                    st.error(str(e))
    else:
        st.warning("No values yet. Upload a text-based report or enter values above.")

# ---------------- Medicine guide ----------------
with tab_med:
    st.warning("Educational guidance for common, mild problems only. It is NOT a prescription "
               "and does not replace a doctor or pharmacist. No doses are given: follow the "
               "product label.")
    sub_symptom, sub_lookup = st.tabs(["🩹 Symptom-based guide", "🔎 Look up a medicine"])

    with sub_symptom:
        syms = st.multiselect("Select your symptoms", list(SYMPTOMS))
        free = st.text_area("Or describe in your own words (optional)",
                            placeholder="e.g. fever and sore throat since yesterday")
        c1, c2 = st.columns(2)
        conditions = c1.multiselect("Health conditions / situations", CONDITIONS)
        days = c2.number_input("Symptoms since (days)", 0, 60, 1)
        allergies = c1.text_input("Known drug allergies", placeholder="e.g. penicillin, aspirin")
        current = c2.text_input("Medicines you already take", placeholder="e.g. crocin, metformin")

        if st.button("💊 Get suggestions"):
            if is_emergency(" ".join(syms) + " " + free):
                st.error(EMERGENCY_MESSAGE)
            else:
                all_syms = sorted(set(syms) | set(detect_symptoms(free)))
                if not all_syms:
                    st.warning("Please select or describe at least one symptom.")
                else:
                    rec = recommend(all_syms, age, conditions, allergies, current, int(days))
                    st.write("**Symptoms considered:** " + ", ".join(all_syms))
                    if rec["age_block"]:
                        st.error(rec["age_block"])
                    else:
                        if rec["red_flags"]:
                            st.error("**See a doctor promptly if:**\n\n" +
                                     "\n".join(f"- {r}" for r in rec["red_flags"]))
                        st.subheader("Options that may suit you")
                        if not rec["options"]:
                            st.info("No safe over-the-counter option could be suggested with "
                                    "your details. Please consult a doctor or pharmacist.")
                        for o in rec["options"]:
                            with st.container(border=True):
                                st.markdown(f"**{o['name']}**  ·  _{o['class']}_")
                                st.caption("For: " + ", ".join(o["for"]))
                                st.write("⚠️ " + o["caution"])
                        if rec["excluded"]:
                            with st.expander("Not suggested for you (and why)"):
                                for e in rec["excluded"]:
                                    st.markdown(f"**{e['name']}**: " + "; ".join(e["reasons"]))
                        with st.expander("General safety notes"):
                            for n in rec["general"]:
                                st.write("- " + n)
                        with st.spinner("Preparing a simple explanation..."):
                            try:
                                st.markdown(ai.medicine_guidance(
                                    all_syms, rec["options"], rec["excluded"], profile, int(days)))
                            except Exception as e:
                                st.info(f"AI explanation unavailable right now: {e}")

    with sub_lookup:
        name = st.text_input("Medicine name", placeholder="e.g. Paracetamol, Metformin, Azithromycin")
        if st.button("Get medicine information") and name.strip():
            with st.spinner("Looking up..."):
                try:
                    st.markdown(ai.medicine_info(name.strip(), profile))
                except Exception as e:
                    st.error(str(e))

# ---------------- History ----------------
with tab_hist:
    st.subheader("Saved reports")
    for r in db.get_reports(sid):
        with st.expander(f"{r['filename']} — {r['created_at']}"):
            st.markdown(r["summary"])
    st.subheader("Chat history")
    for m in db.get_messages(sid):
        st.markdown(f"**{m['role'].title()}** ({m['created_at']}): {m['content']}")
    if st.button("🗑 Clear chat history"):
        db.clear_history(sid)
        st.session_state.messages = []
        st.rerun()
        st.ballon()