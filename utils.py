"""Shared config, paths, logging and helper functions."""
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = DATA_DIR / "chroma_db"
DB_PATH = DATA_DIR / "health_assistant.db"
KB_DIR = BASE_DIR / "knowledge_base"
UPLOAD_DIR = BASE_DIR / "uploads"
for _d in (DATA_DIR, CHROMA_DIR, KB_DIR, UPLOAD_DIR):
    _d.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip()
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

DISCLAIMER = (
    "⚠️ This assistant gives general health information for education only. "
    "It is not a medical diagnosis or a substitute for a doctor."
)

EMERGENCY_MESSAGE = (
    "🚨 **This could be a medical emergency.** Please call your local emergency number "
    "(India: **112** / **108**) or go to the nearest hospital right now. "
    "Do not wait for an online answer."
)

EMERGENCY_PATTERNS = [
    r"chest pain", r"can'?t breathe", r"cannot breathe", r"difficulty breathing",
    r"severe bleeding", r"unconscious", r"stroke", r"seizure", r"heart attack",
    r"suicid", r"kill myself", r"overdose", r"poison",
]


def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return logging.getLogger(name)


def is_emergency(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in EMERGENCY_PATTERNS)


def clean_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def chunk_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph boundaries."""
    text = clean_text(text)
    if not text:
        return []
    chunks, current = [], ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 <= size:
            current = f"{current}\n\n{para}".strip()
            continue
        if current:
            chunks.append(current)
        while len(para) > size:  # very long paragraph
            chunks.append(para[:size])
            para = para[size - overlap:]
        current = para
    if current:
        chunks.append(current)
    return chunks