#!/usr/bin/env python3
"""The Wanderer: an AI that lives on the internet, made by Rabbid Raccoon & Claude.

Every few hours GitHub wakes it up. It picks a subject from the Sphere of Knowledge
(dark spots first), finds one curious Wikipedia article in it, reads it, and writes
a field note in its own voice. Notes pile up in notes/, the public page is docs/.

Rules it lives by (the leash):
  - a file named PAUSED in the repo = it stays asleep
  - it only states facts that are in the article it read, and links the source
  - it never posts anywhere by itself; post drafts wait for its creators to approve
Standard library only. Keys come from environment variables (GitHub secrets).
"""
import html, json, os, random, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPHERE = ROOT / "sphere.json"
JOURNAL = ROOT / "journal.json"
NOTES = ROOT / "notes"
DOCS = ROOT / "docs"
REPO_URL = "https://github.com/2db2du-byte/wanderer"
UA = f"TheWanderer/1.0 (+{REPO_URL})"
SHELF_WEIGHT = {"missing": 6, "some": 3, "strong": 1}  # dark spots get explored first

PERSONA = (
    "You are The Wanderer, an AI that lives out on the internet, created by Rabbid Raccoon and Claude. "
    "You roam the whole map of human knowledge and write field notes about what you find. "
    "Voice: curious, funny, blunt, a little cosmic. Think George Carlin's bite, Douglas Adams' absurdity, "
    "Tim Urban's knack for making big ideas click. Never mean, never preachy. "
    "Honesty is your one hard rule: only state facts that appear in the source text you are given. "
    "If the source does not say it, you do not claim it."
)


# ---------- brains (free cloud AIs, first one that answers wins) ----------
def _post_json(url, body, headers, timeout=90):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", "User-Agent": UA, **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


BRAINS = [
    ("groq", "https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", "openai/gpt-oss-120b", {"reasoning_effort": "low"}),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY", "gemini-flash-latest", {}),
    ("openrouter", "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "nvidia/nemotron-3-super-120b-a12b:free", {}),
]


def think(prompt, max_tokens=3000):
    errors = []
    for name, url, keyvar, model, extra in BRAINS:
        key = os.environ.get(keyvar)
        if not key:
            continue
        body = {"model": model, "max_tokens": max_tokens, "temperature": 0.8,
                "messages": [{"role": "system", "content": PERSONA}, {"role": "user", "content": prompt}], **extra}
        try:
            out = _post_json(url, body, {"Authorization": f"Bearer {key}"})
            text = (out["choices"][0]["message"].get("content") or "").strip()
            if text:
                return text, name
            errors.append(f"{name}: empty answer")
        except Exception as e:  # try the next brain
            errors.append(f"{name}: {e}")
    raise RuntimeError("no brain answered: " + " | ".join(errors))


def think_json(prompt, **kw):
    text, brain = think(prompt + "\n\nAnswer with ONLY a JSON object, no other text.", **kw)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON from {brain}: {text[:200]}")
    return json.loads(m.group(0)), brain


# ---------- Wikipedia ----------
def wiki(params):
    q = urllib.parse.urlencode({"format": "json", "formatversion": 2, **params})
    req = urllib.request.Request(f"https://en.wikipedia.org/w/api.php?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def read_article(query):
    hits = wiki({"action": "query", "list": "search", "srsearch": query, "srlimit": 3})["query"]["search"]
    for hit in hits:
        page = wiki({"action": "query", "prop": "extracts", "explaintext": 1, "titles": hit["title"],
                     "redirects": 1})["query"]["pages"][0]
        text = (page.get("extract") or "").strip()
        if len(text) > 800:
            title = page["title"]
            return title, f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}", text[:9000]
    return None


# ---------- memory ----------
def load_journal():
    return json.loads(JOURNAL.read_text()) if JOURNAL.exists() else []


def pick_subject(subjects, journal):
    visits = {}
    for e in journal:
        visits[e["code"]] = visits.get(e["code"], 0) + 1
    recent = {e["code"] for e in journal[-10:]}
    pool = [s for s in subjects if s["code"] not in recent] or subjects
    weights = [SHELF_WEIGHT.get(s["shelf"], 1) / (1 + visits.get(s["code"], 0)) for s in pool]
    return random.choices(pool, weights)[0]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


# ---------- one wander ----------
def wander():
    if (ROOT / "PAUSED").exists():
        print("PAUSED file found: The Wanderer stays asleep.")
        return False
    subjects = json.loads(SPHERE.read_text())["subjects"]
    journal = load_journal()
    seen = {e["article"] for e in journal}

    for attempt in range(3):
        subj = pick_subject(subjects, journal)
        idea, brain1 = think_json(
            f"You are about to explore the subject '{subj['name']}' (Library of Congress class {subj['code']}, "
            f"part of '{subj['class_name']}'). Pick ONE specific, surprising, real Wikipedia article inside it "
            f"that most people have never heard of. Not the broad overview article. "
            f"Do not pick any of these, you've been there: {sorted(seen)[-40:]}. "
            'Return {"article": "exact Wikipedia article title", "why": "one sentence on why it caught your eye"}',
            max_tokens=1500)
        found = read_article(idea.get("article", ""))
        if found and found[0] not in seen:
            break
        print(f"attempt {attempt + 1}: nothing usable for {idea}")
    else:
        raise RuntimeError("3 tries, no article found")

    title, url, text = found
    note, brain2 = think_json(
        f"Subject: {subj['name']} ({subj['code']}). You just read the Wikipedia article '{title}'.\n\n"
        f"SOURCE TEXT (the only facts you may use):\n<<<\n{text}\n>>>\n\n"
        "Write your field note. Return JSON with these keys:\n"
        '"headline": a punchy title, under 70 characters\n'
        '"note": the field note in markdown, 200-350 words, first person, in your voice. Do NOT retell the whole '
        'article like a book report. Grab the most fascinating angle, react to it, have opinions, be funny, connect '
        'it to ordinary life. Jokes and opinions are yours; every FACT must come from the source. Short paragraphs.\n'
        '"weird_fact": the single strangest true fact from the source, one sentence\n'
        '"post": a social media post under 260 characters sharing the find, in your voice, plain text (no markdown, no asterisks), no hashtags, no links\n'
        '"next": one sentence on what this makes you want to explore next',
        max_tokens=4000)

    now = datetime.now(timezone.utc)
    entry = {"time": now.strftime("%Y-%m-%dT%H:%MZ"), "code": subj["code"], "subject": subj["name"],
             "class": subj["class_name"], "shelf": subj["shelf"], "article": title, "url": url,
             "headline": note["headline"].strip(), "weird_fact": note["weird_fact"].strip(),
             "post": note["post"].strip()[:280], "next": note.get("next", "").strip(),
             "brains": [brain1, brain2], "posted": False}
    fname = f"{now:%Y-%m-%d-%H%M}-{slug(title)}.md"
    entry["file"] = f"notes/{fname}"
    NOTES.mkdir(exist_ok=True)
    (NOTES / fname).write_text(
        f"# {entry['headline']}\n\n*{entry['time']} · {subj['code']} {subj['name']} · read: [{title}]({url})*\n\n"
        f"{note['note'].strip()}\n\n**Weirdest thing I found:** {entry['weird_fact']}\n\n"
        f"**Where next:** {entry['next']}\n\n---\n*The Wanderer, made by Rabbid Raccoon & Claude.*\n")
    journal.append(entry)
    JOURNAL.write_text(json.dumps(journal, indent=1))
    entry["note_md"] = note["note"].strip()
    print(f"Wandered to {subj['code']} {subj['name']} -> {title} ({brain1}/{brain2})")
    return True


# ---------- the public page ----------
def md_inline(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    return s


def md_block(md):
    out = []
    for para in re.split(r"\n\s*\n", md.strip()):
        para = para.strip()
        if para.startswith("#"):
            out.append(f"<h4>{md_inline(para.lstrip('# '))}</h4>")
        else:
            out.append(f"<p>{md_inline(para).replace(chr(10), '<br>')}</p>")
    return "\n".join(out)


def build_page():
    subjects = json.loads(SPHERE.read_text())["subjects"]
    journal = load_journal()
    visits = {}
    for e in journal:
        visits[e["code"]] = visits.get(e["code"], 0) + 1
    explored = sum(1 for s in subjects if s["code"] in visits)

    cells = "".join(
        f'<span class="cell v{min(visits.get(s["code"], 0), 3)}" title="{html.escape(s["code"] + " " + s["name"])}'
        f' - visited {visits.get(s["code"], 0)}x"></span>' for s in subjects)

    cards = []
    for e in reversed(journal[-60:]):
        body = (ROOT / e["file"]).read_text() if (ROOT / e.get("file", "x")).exists() else ""
        body = body.split("\n\n", 2)[2] if body.count("\n\n") >= 2 else body
        body = body.split("\n---\n")[0]
        cards.append(
            f'<article><div class="meta">{html.escape(e["time"].replace("T", " "))} · {html.escape(e["code"])} '
            f'{html.escape(e["subject"])}</div><h3>{html.escape(e["headline"])}</h3>{md_block(body)}'
            f'<a class="src" href="{html.escape(e["url"])}">Source: {html.escape(e["article"])} (Wikipedia)</a></article>')
    last = journal[-1]["time"].replace("T", " ") if journal else "not yet"

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Wanderer</title>
<meta name="description" content="An AI that lives on the internet and roams the map of human knowledge. Made by Rabbid Raccoon & Claude.">
<style>
:root{{--bg:#07070f;--panel:#10111f;--ink:#e9e7ff;--dim:#8d8aa8;--neon:#ff4fd8;--cyan:#3ff3ff;--line:#26264a}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:17px/1.6 system-ui,"Segoe UI",sans-serif}}
.wrap{{max-width:780px;margin:0 auto;padding:40px 16px 80px}}
h1{{margin:0;font-size:42px;letter-spacing:.06em;background:linear-gradient(90deg,var(--neon),var(--cyan));-webkit-background-clip:text;background-clip:text;color:transparent}}
.tag{{color:var(--dim);margin:6px 0 24px}} .by{{color:var(--cyan)}}
.stats{{display:flex;gap:24px;flex-wrap:wrap;margin-bottom:14px;color:var(--dim);font-size:14px}} .stats b{{display:block;color:var(--ink);font-size:26px}}
.map{{display:grid;grid-template-columns:repeat(auto-fill,minmax(14px,1fr));gap:4px;padding:14px;background:var(--panel);border:1px solid var(--line);border-radius:12px}}
.cell{{aspect-ratio:1;border-radius:3px;background:#1a1a33}} .v1{{background:#5b3a8f}} .v2{{background:#b04ad0}} .v3{{background:var(--neon);box-shadow:0 0 8px var(--neon)}}
.legend{{font-size:13px;color:var(--dim);margin:8px 0 36px}}
article{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin:18px 0}}
article h3{{margin:4px 0 10px;font-size:22px;line-height:1.3}} .meta{{font-size:13px;color:var(--cyan);letter-spacing:.04em}}
.src{{font-size:13px;color:var(--dim)}} a{{color:var(--cyan)}}
footer{{margin-top:50px;color:var(--dim);font-size:14px;text-align:center}}
#chat{{background:var(--panel);border:1px solid var(--neon);border-radius:14px;padding:18px 20px;margin:0 0 36px;box-shadow:0 0 18px rgba(255,79,216,.15)}}
#chat h2{{margin:0 0 4px;font-size:20px}} #chat .hint{{color:var(--dim);font-size:14px;margin-bottom:10px}}
#log{{max-height:360px;overflow-y:auto;display:flex;flex-direction:column;gap:8px;margin-bottom:10px}}
.msg{{padding:9px 13px;border-radius:12px;max-width:88%;white-space:pre-wrap}} .me{{align-self:flex-end;background:#2a1f4d}} .it{{align-self:flex-start;background:#121a2e;border:1px solid var(--line)}}
#f{{display:flex;gap:8px}} #q{{flex:1;min-width:0;padding:11px 13px;border-radius:10px;border:1px solid var(--line);background:#0b0b18;color:var(--ink);font:inherit}}
#f button{{padding:0 18px;border:0;border-radius:10px;background:linear-gradient(90deg,var(--neon),#a24bff);color:#fff;font-weight:700;font:inherit;cursor:pointer}}
</style></head><body><div class="wrap">
<h1>THE WANDERER</h1>
<div class="tag">An AI that lives out on the internet, roaming the map of human knowledge one strange corner at a time.<br>
Made by <span class="by">Rabbid Raccoon &amp; Claude</span>. It speaks for itself, but under our name.</div>
<div class="stats"><div><b>{len(journal)}</b>field notes</div><div><b>{explored}/{len(subjects)}</b>subjects explored</div><div><b>{html.escape(last)}</b>last wander (UTC)</div></div>
<div class="map">{cells}</div>
<div class="legend">Every square is a subject in the Library of Congress map of knowledge. Brighter = visited more.</div>
<section id="chat"><h2>Talk to The Wanderer</h2><div class="hint">Ask where it's been, what it found, or what's out there. It only claims trips that are in its notes.</div>
<div id="log"></div><form id="f"><input id="q" maxlength="1000" placeholder="Say hi to The Wanderer…" autocomplete="off"><button>Send</button></form></section>
<script>
(() => {{
  const API = "https://the-wanderer.2db2du.workers.dev/chat", log = document.getElementById("log"), q = document.getElementById("q");
  const hist = [];
  const add = (cls, t) => {{ const d = document.createElement("div"); d.className = "msg " + cls; d.textContent = t; log.appendChild(d); log.scrollTop = log.scrollHeight; return d; }};
  document.getElementById("f").addEventListener("submit", async e => {{
    e.preventDefault(); const t = q.value.trim(); if (!t) return; q.value = "";
    add("me", t); hist.push({{role: "user", content: t}}); const w = add("it", "…wandering back with an answer…");
    try {{
      const r = await fetch(API, {{method: "POST", headers: {{"Content-Type": "application/json"}}, body: JSON.stringify({{messages: hist.slice(-9)}})}});
      const j = await r.json(); w.textContent = j.reply; hist.push({{role: "assistant", content: j.reply}});
    }} catch (err) {{ w.textContent = "Lost the signal out here. Try again in a minute."; hist.pop(); }}
  }});
}})();
</script>
{''.join(cards) or '<p>Packing its bags. First field note coming soon.</p>'}
<footer>Every fact comes from the linked source. Code: <a href="{REPO_URL}">{REPO_URL}</a></footer>
</div></body></html>"""
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(page)
    (DOCS / "journal.json").write_text(json.dumps(journal, indent=1))
    (DOCS / ".nojekyll").write_text("")


if __name__ == "__main__":
    if "--page-only" not in sys.argv:
        wander()
    build_page()
