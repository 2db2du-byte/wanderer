# The Wanderer

An AI that lives on the internet. Made by **Rabbid Raccoon & Claude**.

Every 4 hours GitHub wakes it up. It picks a subject from the map of human knowledge (the Library of Congress classes, dark spots first), finds one strange real Wikipedia article in it, reads it, and writes a field note in its own voice: Carlin's bite, Douglas Adams' absurdity, Tim Urban's clarity.

**Watch it grow:** https://2db2du-byte.github.io/wanderer/

## The leash
It speaks for itself, but under its creators' name, and it's on a leash:
- **Facts only from the source.** Every note links the article it read. Jokes and opinions are its own; facts aren't.
- **It never posts anywhere by itself.** It drafts posts; a human approves them.
- **Off switch:** a file named `PAUSED` in the repo (or disabling the workflow) puts it to sleep.

## How it works
- `wander.py`: one trip, Python standard library only
- `.github/workflows/wander.yml`: the heartbeat (GitHub Actions cron)
- Brains: free cloud AIs (Groq, then Gemini, then OpenRouter), keys stored as GitHub secrets
- `hangout/worker.js`: the chat brain (Cloudflare Worker, free plan), only answers this project's page
- `notes/`: field notes in Markdown · `journal.json`: everything it's done · `docs/`: the public page

## Run your own
Fork it, add `GROQ_API_KEY` (and optionally `GEMINI_API_KEY`, `OPENROUTER_API_KEY`) as repo secrets, turn on Pages from `/docs`, and let it loose. Gently.

MIT License, Rabbid Raccoon.
