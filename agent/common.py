"""Settings shared by the agent and the page server: the local LiveKit dev server's
keys, and the OpenAI key read from the monorepo's backend .env (never printed)."""
import os
import re
from pathlib import Path

LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")        # `livekit-server --dev`
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
ENV_FILE = Path(os.environ.get("OPENAI_ENV_FILE", "/Users/mabab/projects/allright/backend/env/.env"))


def load_env():
    os.environ.setdefault("LIVEKIT_URL", LIVEKIT_URL)
    os.environ.setdefault("LIVEKIT_API_KEY", LIVEKIT_API_KEY)
    os.environ.setdefault("LIVEKIT_API_SECRET", LIVEKIT_API_SECRET)
    if not os.environ.get("OPENAI_API_KEY") and ENV_FILE.exists():
        m = re.search(r"^OPENAI_API_KEY=(.*)$", ENV_FILE.read_text(), re.M)
        if m:
            os.environ["OPENAI_API_KEY"] = m.group(1).strip().strip("\"'")
