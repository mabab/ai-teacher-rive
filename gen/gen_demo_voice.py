#!/usr/bin/env python3
"""The teacher's lines for the emulated lesson (web/index.html, when no agent server is reachable):
the same voice as agent/tutor.py (gpt-4o-mini-tts, coral). Output: web/demo/t<i>.mp3
Run: python3 gen/gen_demo_voice.py
"""
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "demo"
KEY = os.environ.get("OPENAI_API_KEY") or re.search(r"^OPENAI_API_KEY=(.*)$", Path(os.environ.get(
    "OPENAI_ENV_FILE", "/Users/mabab/projects/allright/backend/env/.env")).read_text(), re.M).group(1).strip().strip("\"'")
VOICE = "A cheerful, patient primary-school teacher. Speak clearly and a little slowly."
LINES = [
    "Hi there! My name is Olena, and I'm your English teacher. What's your name?",
    "Nice to meet you, Sasha! Let's talk about animals. What animal do you like?",
    "Cats are great! Can you say: the cat is small? Скажи: кіт маленький.",
    "Wonderful, well done! And what colour is your cat?",
    "A black and white cat, how lovely! You speak English very well. See you next time!",
]

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for i, text in enumerate(LINES, start=1):
        body = json.dumps({"model": "gpt-4o-mini-tts", "voice": "coral", "input": text, "instructions": VOICE, "response_format": "mp3"})
        subprocess.run(["curl", "-s", "https://api.openai.com/v1/audio/speech", "-H", f"Authorization: Bearer {KEY}",
                        "-H", "Content-Type: application/json", "-d", body, "-o", str(OUT / f"t{i}.mp3")], check=True)
        print("ok", i)
