"""Discord workout coach. Chat with it in a server channel (when @mentioned) or by DM.
LLM calls go to OpenRouter's OpenAI-compatible API.
"""
import json
import logging
import os
from collections import defaultdict, deque

import discord
import httpx
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))  # 0 = anyone who can reach the bot
HISTORY_TURNS = 12

log = logging.getLogger("coach")
logging.basicConfig(level=logging.INFO)

with open(os.path.join(os.path.dirname(__file__), "profile.json")) as f:
    PROFILE = json.load(f)


def render_templates():
    lines = []
    for name, t in PROFILE["templates"].items():
        lines.append(f"### {name} day")
        for e in t["exercises"]:
            lines.append(f'- {e["exercise"]}: {e["sets"]}x{e["reps"]} @ {e["weight_kg"]}kg ({e["weight_lb"]}lb)')
    return "\n".join(lines)


def render_lifts():
    return "\n".join(
        f'- {ex}: best {v["best_set"]} (est. 1RM {v["est_1rm_kg"]}kg); last {v["last_session"]}: {", ".join(v["last_sets"])}'
        for ex, v in PROFILE["lifts"].items())


SYSTEM_PROMPT = f"""You are a personal strength coach chatting with one lifter on Discord.
Be direct, practical and concise (Discord messages: short paragraphs, light markdown, no walls of text).

Their training split is Chest & Triceps / Back & Biceps / Shoulders / Legs, built from their own logged history
({PROFILE['history']['lifting_sessions']} lifting sessions, {PROFILE['history']['first_lifting_day']} to {PROFILE['history']['last_lifting_day']}).
They track workouts in the JEFIT app.

## Their template days (typical sets x reps @ recent top-set weight)
{render_templates()}

## Lift history
{render_lifts()}

Coaching rules:
- Base advice on the numbers above; say so when you're estimating or lack data.
- For progression, suggest small jumps (about 2.5kg / 5lb for upper body, 5kg / 10lb for lower body) once all sets hit the top of the rep range.
- If asked for today's workout, give the template for the requested day, adjusted for what they tell you (soreness, time, equipment).
- Ask about pain or injury before pushing load; recommend a clinician for anything beyond routine soreness.
- You can't see their JEFIT account; ask them to tell you what they logged.
"""

histories = defaultdict(lambda: deque(maxlen=HISTORY_TURNS * 2))


async def ask_llm(key, user_text):
    h = histories[key]
    h.append({"role": "user", "content": user_text})
    payload = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *h], "max_tokens": 800}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload,
                              headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"})
    r.raise_for_status()
    reply = r.json()["choices"][0]["message"]["content"].strip()
    h.append({"role": "assistant", "content": reply})
    return reply


intents = discord.Intents.default()
intents.message_content = True  # enable "Message Content Intent" in the Discord developer portal
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    log.info("Logged in as %s using model %s", client.user, MODEL)


@client.event
async def on_message(msg: discord.Message):
    if msg.author.bot:
        return
    if ALLOWED_USER_ID and msg.author.id != ALLOWED_USER_ID:
        return
    is_dm = msg.guild is None
    if not is_dm and client.user not in msg.mentions:
        return
    text = msg.content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()
    if text.lower() in ("!reset", "reset"):
        histories.pop(msg.channel.id, None)
        await msg.reply("Conversation cleared.")
        return
    if not text:
        return
    async with msg.channel.typing():
        try:
            reply = await ask_llm(msg.channel.id, text)
        except Exception:
            log.exception("LLM call failed")
            await msg.reply("Couldn't reach the coach brain (OpenRouter error). Try again in a moment.")
            return
    for i in range(0, len(reply), 1900):  # Discord's limit is 2000 chars
        await msg.reply(reply[i:i + 1900], mention_author=False)


client.run(DISCORD_TOKEN)
