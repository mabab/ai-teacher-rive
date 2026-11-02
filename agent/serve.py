"""Serves the page (../web) and hands out a token for a fresh room; the agent
joins every new room on its own (automatic dispatch).

Run: .venv/bin/python serve.py   -> http://127.0.0.1:8773 (Rive), http://127.0.0.1:8773/3d/ (3D, when talkinghead/ is there)
"""
import secrets
from pathlib import Path

from aiohttp import web
from livekit import api

from common import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL

WEB = Path(__file__).resolve().parent.parent / "web"
TH = Path(__file__).resolve().parent.parent / "talkinghead" / "web"   # the 3D (TalkingHead) prototype at /3d/


async def token(_request):
    room = f"tutor-{secrets.token_hex(3)}"
    identity = f"student-{secrets.token_hex(3)}"
    jwt = (api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
           .with_identity(identity).with_name("Учень")
           .with_grants(api.VideoGrants(room_join=True, room=room))
           .to_jwt())
    return web.json_response({"url": LIVEKIT_URL, "token": jwt, "room": room})


async def index(_request):
    return web.FileResponse(WEB / "index.html")


app = web.Application()
app.router.add_post("/token", token)
app.router.add_get("/", index)
if TH.exists():                                     # not in the published repo
    app.router.add_get("/3d/", lambda _r: web.FileResponse(TH / "index.html"))
    app.router.add_static("/3d/", TH)
app.router.add_static("/", WEB)

if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1", port=8773)
