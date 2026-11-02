"""A small English tutor agent for kids, enough to walk the Rive teacher through
every lk.agent.state (initializing, idle, listening, thinking, speaking).

Run: .venv/bin/python tutor.py dev   (with `livekit-server --dev` running)
"""
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli
from livekit.plugins import openai, silero

from common import load_env

load_env()

INSTRUCTIONS = """You are Olena, a warm and playful English teacher for Ukrainian kids aged 6 to 10.
Speak simple English in short sentences, one idea at a time, and ask one question per turn.
If the child seems lost, add a short hint in Ukrainian. Praise effort. Never talk about yourself as an AI.
Keep every reply under three sentences: this is a spoken lesson."""

# a local demo on a busy laptop: never turn a lesson away because the CPU is loaded
server = AgentServer(load_threshold=float("inf"))


@server.rtc_session()
async def entrypoint(ctx: JobContext):
    await ctx.connect()
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=openai.STT(model="gpt-4o-mini-transcribe", language="en"),
        llm=openai.LLM(model="gpt-4.1-mini"),
        tts=openai.TTS(model="gpt-4o-mini-tts", voice="coral",
                       instructions="A cheerful, patient primary-school teacher. Speak clearly and a little slowly."),
    )
    await session.start(room=ctx.room, agent=Agent(instructions=INSTRUCTIONS))
    await session.generate_reply(instructions="Greet the child, say your name is Olena, and ask their name.")


if __name__ == "__main__":
    cli.run_app(server)
