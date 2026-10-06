"""Run:  python test_api.py   -> checks your key and lists usable models."""
from ai_engine import AIEngine

try:
    ai = AIEngine()
    models = ai.list_models()
    print("Models that support generateContent:")
    for m in models:
        print("  ", m)
    print("\nAuto-selected:", ai._pick_model())
    print("\nTest reply:", ai._generate("Say 'API working' in 3 words.", max_tokens=50))
except Exception as e:
    print("FAILED:", e)