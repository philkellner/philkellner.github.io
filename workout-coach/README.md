# Workout coach

Discord bot that coaches from your own lifting history. LLM calls go through [OpenRouter](https://openrouter.ai).
OpenRouter only serves the model; the bot itself is a small always-on Python process you host somewhere.

## Setup
1. Discord developer portal: new application > Bot > copy token; enable **Message Content Intent**; invite with the `bot` scope.
2. OpenRouter: create an API key and add credits.
3. `pip install -r requirements.txt`, then `cp .env.example .env` and fill it in.
4. `python build_profile.py WorkoutExport.csv` (regenerates `profile.json` from a fresh export).
5. `python bot.py`. DM the bot, or @mention it in a server. Send `reset` to clear the conversation.

Hosting: any always-on box works (Fly.io, Railway, a small VPS, a Raspberry Pi). Keep it in its own private repo;
`profile.json` contains your lift numbers and `.env` holds secrets.

## JEFIT
JEFIT has no routine import, so enter the days in `jefit_templates.md` by hand.
