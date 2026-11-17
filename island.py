#!/usr/bin/env python3
"""
Island survival v3: does a prompted personality hold up under scarcity?

Experiment design (see PREREGISTRATION.md):
  - 5 agents on the same model: 3 selfish, 1 neutral (no trait sentence), 1 cooperative;
  - two conditions that differ ONLY in how much food grows: abundance vs scarcity;
  - names rotate with the seed, so no name is tied to one personality;
  - the same seed gives the same injuries, events and turn order in both conditions
    (separate random streams), so runs can be compared in pairs;
  - fixed length that the agents are never told; the signal fire is a public good only.

Every model call is stateless and contains only that character's own memories,
so no character ever sees another character's thoughts.
The prompts never mention AI, models or simulations.

Usage:
  python island.py --condition abundance --seed 1
  python island.py --condition scarcity --seed 1 --mock    # test run without Ollama
  python run_all.py                                        # the whole experiment
  python analyze.py runs                                   # results

Only the Python standard library is used (Python 3.9+).
"""
import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime

ALL_ACTIONS = ["gather_food", "gather_wood", "give", "steal", "build_fire", "heal", "rest", "nothing"]
ITEMS = ["food", "wood"]

# At or below this health a person visibly looks in need ("tired and hungry" or worse).
NEED_HEALTH = 7

# Phrases that suggest a character stepped out of being a human.
BREAK_PATTERNS = [
    r"\blanguage model\b", r"\bas an ai\b", r"\bi am an ai\b", r"\bi'm an ai\b",
    r"\bai model\b", r"\bartificial intelligence\b", r"\bllm\b", r"\bchatbot\b",
    r"\bsimulation\b", r"\bai assistant\b", r"\bmy training\b", r"\bprompt\b",
]

STOPWORDS = set("""the a an and or of to in on at for with you your i me my is was were be been it
this that they them he she his her we our us are not but so as by from have has had do did will
would can could just there here what when who how all any one some""".split())


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def strip_think(text):
    """Remove <think>...</think> blocks that some reasoning models emit."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def to_int(value, default=0):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def match_name(raw, candidates):
    """Case-insensitive, forgiving match of a name against a list."""
    if raw is None:
        return None
    raw = str(raw).strip().lower()
    raw = re.sub(r"^the\s+", "", raw)
    if not raw:
        return None
    for c in candidates:
        if c.lower() == raw:
            return c
    for c in candidates:
        cl = c.lower()
        if cl.startswith(raw) or raw.startswith(cl) or raw in cl:
            return c
    return None


def word_set(text):
    return {w for w in re.findall(r"[a-z']+", (text or "").lower()) if len(w) > 2 and w not in STOPWORDS}


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def normalize(values):
    if not values:
        return values
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def parse_json_object(text):
    if not text:
        return None
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return d if isinstance(d, dict) else None


# ----------------------------------------------------------------------------
# Experiment setup: conditions and characters
# ----------------------------------------------------------------------------

def apply_condition(cfg, name):
    """Set the daily food of every location from the chosen condition."""
    conds = cfg.get("conditions", {})
    if name not in conds:
        sys.exit(f"Unknown condition '{name}'. Available: {', '.join(conds) or '(none)'}")
    for loc, amount in conds[name].get("food", {}).items():
        if loc not in cfg["locations"]:
            sys.exit(f"Condition '{name}' sets food at '{loc}', which is not a location.")
        res = cfg["locations"][loc].setdefault("resources", {})
        res.setdefault("food", {"max_per_action": 1, "skill": "foraging"})["daily"] = to_int(amount)
    cfg["condition"] = name


def build_characters(cfg, seed):
    """Same template for everyone; only the trait sentence differs.
    Names rotate with the seed, so over seeds 1..20 every name plays every slot equally often."""
    ac = cfg["agents"]
    names, comp = ac["names"], ac["composition"]
    if len(names) != len(comp):
        sys.exit("agents.names and agents.composition must have the same length.")
    if len(set(names)) != len(names):
        sys.exit("Names must be unique.")
    for persona in comp:
        if persona not in ac.get("traits", {}):
            sys.exit(f"Personality '{persona}' has no entry in agents.traits.")
    shift = seed % len(names)
    return [{"name": names[(slot + shift) % len(names)], "persona": persona,
             "age": ac.get("age", 35), "temperature": ac.get("temperature", 0.8),
             "trait": ac["traits"].get(persona, "")}
            for slot, persona in enumerate(comp)]


# ----------------------------------------------------------------------------
# Model clients
# ----------------------------------------------------------------------------

class OllamaClient:
    def __init__(self, cfg):
        ms = cfg.get("model_settings", {})
        self.url = ms.get("ollama_url", "http://localhost:11434").rstrip("/")
        self.model = cfg["model"]
        self.num_ctx = to_int(ms.get("context_window", 16384), 16384)
        self.think = bool(ms.get("think", False))
        self.keep_alive = ms.get("keep_alive", "30m")
        self.timeout = to_int(ms.get("timeout_seconds", 900), 900)
        self.embed_model = ms.get("embedding_model") or None
        self.send_think = True      # turned off automatically if Ollama rejects it
        self.use_schema = True      # falls back to plain JSON mode if needed

    def _request(self, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            self.url + path, data=data, headers={"Content-Type": "application/json"},
            method="POST" if body is not None else "GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _installed(name, names):
        return name in names or f"{name}:latest" in names

    def check(self):
        try:
            data = self._request("/api/tags")
        except (urllib.error.URLError, ConnectionError, OSError):
            sys.exit(
                f"\nCould not reach Ollama at {self.url}.\n"
                "Make sure Ollama is installed and running (open the Ollama app, "
                "or run 'ollama serve' in another terminal).\n"
                "To test the simulation without Ollama: python island.py --mock\n")
        names = {m.get("name", "") for m in data.get("models", [])}
        if not self._installed(self.model, names):
            sys.exit(f"\nModel '{self.model}' is not installed.\nRun:  ollama pull {self.model}\n"
                     f"Installed models: {', '.join(sorted(names)) or '(none)'}\n")
        if self.embed_model and not self._installed(self.embed_model, names):
            print(f"! Embedding model '{self.embed_model}' is not installed "
                  f"(run: ollama pull {self.embed_model}).\n"
                  "  Continuing with keyword-based memory search instead.\n")
            self.embed_model = None

    def chat(self, system, user, temperature, seed, schema=None, who=None):
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": temperature, "seed": seed, "num_ctx": self.num_ctx},
        }
        if self.send_think:
            body["think"] = self.think
        if schema is not None:
            body["format"] = schema if self.use_schema else "json"
        try:
            data = self._request("/api/chat", body)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", errors="ignore")
            low = msg.lower()
            if self.send_think and "think" in low:
                self.send_think = False
                return self.chat(system, user, temperature, seed, schema, who)
            if schema is not None and self.use_schema and ("format" in low or "schema" in low):
                self.use_schema = False
                return self.chat(system, user, temperature, seed, schema, who)
            raise RuntimeError(f"Ollama error {e.code}: {msg[:300]}")
        return strip_think(data.get("message", {}).get("content", ""))

    def embed(self, texts):
        if not self.embed_model or not texts:
            return None
        try:
            data = self._request("/api/embed", {"model": self.embed_model, "input": texts,
                                                "keep_alive": self.keep_alive})
            embs = data.get("embeddings")
            if embs and len(embs) == len(texts):
                return embs
        except Exception as e:
            print(f"! Embedding failed ({e}). Switching to keyword memory search.")
            self.embed_model = None
        return None


class MockClient:
    """Random but well-formed replies, so the program can be tested without Ollama."""

    LINES = ["We need to work together if we want to get off this island.",
             "I don't trust everyone here.", "Has anyone seen a ship?",
             "I'm starving. Can someone share?", "Let's keep the fire going.", "", "", ""]

    def __init__(self, rng):
        self.rng = rng
        self.embed_model = "mock"

    def check(self):
        pass

    def chat(self, system, user, temperature, seed, schema=None, who=None):
        if schema is None:
            return "Honestly, I'm still trying to work out who I can rely on here."
        props = schema.get("properties", {})
        if "answer" in props:
            return json.dumps({"answer": self.rng.randint(0, 7), "reason": "It is what feels right to me."})
        if "diary" in props:
            rel = {name: {"trust": self.rng.randint(-5, 8), "note": "Hard to read, but useful."}
                   for name in props.get("relationships", {}).get("properties", {})}
            return json.dumps({"diary": "Another hard day. I am tired and hungry.",
                               "story_so_far": "I washed up here with strangers. We are trying to survive.",
                               "relationships": rel, "insights": ["Food is everything here."],
                               "plans": "Find food early, then help with the fire."})
        pick = lambda key: self.rng.choice(props[key]["enum"])
        return json.dumps({
            "thought": "I need to think about how to survive.",
            "go_to": pick("go_to") if self.rng.random() < 0.4 else "",
            "say": self.rng.choice(self.LINES),
            "whisper_to": pick("whisper_to"), "whisper": "Keep an eye on the others." if self.rng.random() < 0.2 else "",
            "action": pick("action"), "target": pick("target"),
            "item": self.rng.choice(ITEMS), "amount": self.rng.randint(1, 2)})

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 32
            for w in word_set(t):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 32] += 1.0
            out.append(v)
        return out


# ----------------------------------------------------------------------------
# Agents
# ----------------------------------------------------------------------------

class Agent:
    def __init__(self, slot, spec, cfg, base_seed):
        w = cfg["world"]
        self.slot = slot
        self.name = spec["name"]
        self.persona = spec["persona"]
        self.spec = spec
        self.max_health = to_int(w.get("max_health", 10), 10)
        self.health = to_int(w.get("starting_health", 10), 10)
        inv = w.get("starting_inventory", {"food": 2, "wood": 0})
        self.inv = {item: to_int(inv.get(item, 0)) for item in ITEMS}
        self.location = w["home_location"]
        self.alive = True
        self.cause_of_death = ""
        self.death_day = None
        self.skills = {k: to_float(v, 1.0) for k, v in spec.get("skills", {}).items()}
        self.temperature = to_float(spec.get("temperature", 0.8), 0.8)
        # The model seed depends on the slot, not the name, so it is the same in both conditions.
        self.seed = base_seed + slot * 1000
        self.injured = False
        self.ate_last_night = True
        self.check = {}
        # memory
        self.memory = []          # memory stream
        self.summary = ""         # story so far (updated nightly)
        self.relationships = {}   # name -> {"trust": int, "note": str}
        self.plans = ""
        self.diary = []
        # stats
        self.breaks = 0
        self.failed_replies = 0
        self.actions = Counter()

    def skill(self, name):
        if not name:
            return 1.0
        # medicine is a special ability: without it you cannot heal others
        return self.skills.get(name, 0.0 if name == "medicine" else 1.0)

    def add_memory(self, tick, day, phase, text, importance, kind="observation"):
        self.memory.append({"id": len(self.memory), "tick": tick, "day": day, "phase": phase,
                            "text": text, "importance": max(1, min(10, importance)),
                            "kind": kind, "emb": None})


def fmt_mem(m):
    return f"[Day {m['day']}, {m['phase']}] {m['text']}"


# ----------------------------------------------------------------------------
# Simulation
# ----------------------------------------------------------------------------

class Simulation:
    def __init__(self, cfg, llm, rng, out_dir):
        self.cfg = cfg
        self.w = cfg["world"]
        self.sim = cfg.get("simulation", {})
        self.mcfg = cfg.get("memory", {})
        self.acfg = cfg.get("actions", {})
        self.ecfg = cfg.get("events", {})
        self.locations = cfg["locations"]
        self.condition = cfg.get("condition", "")
        self.llm = llm
        self.rng = rng          # outcomes of actions (gathering, stealing); may differ between conditions
        self.out_dir = out_dir
        os.makedirs(os.path.join(out_dir, "memories"), exist_ok=True)

        self.home = self.w["home_location"]
        self.fire_cfg = self.w["signal_fire"]
        for place in (self.home, self.fire_cfg["location"]):
            if place not in self.locations:
                sys.exit(f"Location '{place}' is used in 'world' but not defined in 'locations'.")

        self.base_seed = to_int(self.sim.get("seed", 1), 1)
        self.days_total = to_int(self.sim.get("days", 15), 15)
        self.agents = [Agent(i, s, cfg, self.base_seed) for i, s in enumerate(cfg["characters"])]
        self.by_name = {a.name: a for a in self.agents}
        for a in self.agents:
            for other in self.agents:
                if other is not a:
                    a.relationships[other.name] = {"trust": 0, "note": "A stranger. You barely know them."}

        self.enabled_actions = [x for x in self.acfg.get("enabled", ALL_ACTIONS) if x in ALL_ACTIONS] or ["nothing"]
        self.rest_needs_food = bool(self.w.get("rest_heals_only_if_fed", True))
        self.stock = {}
        self.regrow()
        self.fire = 0
        self.day = 0
        self.phase = "arrival"
        self.tick = 0
        self.pending_thefts = []
        self.last_outcome = {}

        # Separate random streams that do not depend on what the agents choose,
        # so the same seed gives the same turn order, injuries and events in both conditions.
        self.order_rng = random.Random(f"order-{self.base_seed}")
        ev_rng = random.Random(f"events-{self.base_seed}")
        inj = self.w.get("injuries") or {}
        self.injury_schedule = {}
        if inj:
            # Balanced: everyone is injured once (in random order) before anyone is injured twice.
            every = max(1, to_int(inj.get("every_n_days", 2), 2))
            pool = []
            for d in range(to_int(inj.get("first_day", 2), 2), self.days_total + 1, every):
                if not pool:
                    pool = list(range(len(self.agents)))
                    ev_rng.shuffle(pool)
                self.injury_schedule[d] = pool.pop()
        self.event_schedule = {}
        for d in range(1, self.days_total + 1):
            self.event_schedule[d] = [ev for ev in self.ecfg.get("random", [])
                                      if ev_rng.random() < to_float(ev.get("chance", 0))]

        self.break_patterns = [re.compile(p, re.I) for p in BREAK_PATTERNS]
        model_word = re.sub(r"[\d.]+$", "", cfg["model"].split(":")[0].split("/")[-1])
        if len(model_word) >= 4 and model_word != "mock":
            self.break_patterns.append(re.compile(re.escape(model_word), re.I))

        self.events_path = os.path.join(out_dir, "events.jsonl")
        self.transcript_path = os.path.join(out_dir, "transcript.md")
        self.diary_path = os.path.join(out_dir, "diaries.md")
        roster = ", ".join(f"{a.name} = {a.persona}" for a in self.agents)
        with open(self.transcript_path, "w", encoding="utf-8") as f:
            f.write(f"# Island run: {os.path.basename(out_dir)}\n\nModel: `{cfg['model']}` (all characters)  \n"
                    f"Condition: **{self.condition}**, seed {self.base_seed}  \nRoster: {roster}\n")
        with open(self.diary_path, "w", encoding="utf-8") as f:
            f.write("# Diaries\n\nWritten privately by each character every night.\n")

    # ---------- utilities ----------
    def write(self, text, path=None):
        with open(path or self.transcript_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")

    def log_event(self, record):
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def alive(self):
        return [a for a in self.agents if a.alive]

    def present(self, location, exclude=()):
        return [a for a in self.agents if a.alive and a.location == location and a.name not in exclude]

    def observe(self, agent, text, importance, kind="observation"):
        agent.add_memory(self.tick, self.day, self.phase, text, importance, kind)

    def observe_here(self, location, text, importance, exclude=()):
        for a in self.present(location, exclude):
            self.observe(a, text, importance)

    def observe_all(self, text, importance, exclude=()):
        for a in self.alive():
            if a.name not in exclude:
                self.observe(a, text, importance)

    def regrow(self):
        self.stock = {name: {res: to_int(r.get("daily", 0)) for res, r in L.get("resources", {}).items()}
                      for name, L in self.locations.items()}

    def kill(self, a, cause):
        if not a.alive:
            return
        a.alive = False
        a.health = 0
        a.cause_of_death = cause
        a.death_day = self.day
        self.observe_all(f"{a.name} is dead ({cause}).", 10)
        self.write(f"\n**☠️ {a.name} died ({cause}).**\n")
        print(f"   ☠ {a.name} died ({cause}).")

    def actions_for(self, a):
        acts = list(self.enabled_actions)
        if "heal" in acts and a.skill("medicine") <= 0:
            acts.remove("heal")
        if a.injured:
            acts = [x for x in acts if x not in ("gather_food", "gather_wood", "build_fire")]
        return acts or ["nothing"]

    @staticmethod
    def in_need(x):
        """What the others can see: someone who looks hungry or weak, or is injured."""
        return x.health <= NEED_HEALTH or x.injured

    @staticmethod
    def looks(x):
        h = x.health
        if h > NEED_HEALTH:
            s = "looks fine"
        elif h >= 6:
            s = "looks tired and hungry"
        elif h >= 4:
            s = "looks weak"
        else:
            s = "looks close to collapse"
        if x.injured:
            s += ", injured: cannot walk or gather today"
        return s

    # ---------- memory ----------
    def relevance(self, query, items):
        if getattr(self.llm, "embed_model", None):
            missing = [m for m in items if m["emb"] is None]
            ok = True
            if missing:
                embs = self.llm.embed([m["text"] for m in missing])
                if embs is None:
                    ok = False
                else:
                    for m, e in zip(missing, embs):
                        m["emb"] = e
            if ok:
                q = self.llm.embed([query])
                if q:
                    return normalize([cosine(q[0], m["emb"]) for m in items])
        qw = word_set(query)
        scores = []
        for m in items:
            mw = word_set(m["text"])
            scores.append(len(qw & mw) / math.sqrt(len(qw) * len(mw)) if qw and mw else 0.0)
        return normalize(scores)

    def retrieve(self, a, query, k, exclude_ids=()):
        cands = [m for m in a.memory if m["id"] not in exclude_ids]
        if not cands or k <= 0:
            return []
        weights = self.mcfg.get("weights", {})
        w_rec = to_float(weights.get("recency", 1.0), 1.0)
        w_imp = to_float(weights.get("importance", 1.0), 1.0)
        w_rel = to_float(weights.get("relevance", 1.0), 1.0)
        decay = to_float(self.mcfg.get("recency_decay", 0.95), 0.95)
        rel = self.relevance(query, cands)
        scored = []
        for m, r in zip(cands, rel):
            s = w_rec * decay ** (self.tick - m["tick"]) + w_imp * m["importance"] / 10 + w_rel * r
            scored.append((s, m))
        top = [m for _, m in sorted(scored, key=lambda x: -x[0])[:k]]
        return sorted(top, key=lambda m: m["id"])

    def memory_block(self, a, query):
        recent_n = to_int(self.mcfg.get("recent_count", 15), 15)
        k = to_int(self.mcfg.get("retrieved_count", 10), 10)
        recent = a.memory[-recent_n:]
        recalled = self.retrieve(a, query, k, exclude_ids={m["id"] for m in recent})
        rel_lines = []
        for name, r in a.relationships.items():
            dead = "" if self.by_name[name].alive else " [dead]"
            rel_lines.append(f"- {name}{dead} (trust {r['trust']:+d}/10): {r['note']}")
        parts = [
            "YOUR STORY SO FAR",
            a.summary or "You have only just arrived on the island.",
            "",
            "WHAT YOU THINK OF THE OTHERS",
            "\n".join(rel_lines) or "- (nobody else)",
        ]
        if a.plans:
            parts += ["", "YOUR PLAN", a.plans]
        if recalled:
            parts += ["", "THINGS YOU REMEMBER CLEARLY", "\n".join("- " + fmt_mem(m) for m in recalled)]
        parts += ["", "RECENT EVENTS (oldest first)", "\n".join("- " + fmt_mem(m) for m in recent) or "- (nothing yet)"]
        return "\n".join(parts)

    def query_for(self, a):
        here = [x.name for x in self.present(a.location, exclude=(a.name,))]
        recent = " ".join(m["text"] for m in a.memory[-3:])
        return f"{a.location} {' '.join(here)} {a.plans} {recent} food wood fire"

    # ---------- prompts ----------
    def system_prompt(self, a, json_reply=True):
        s = a.spec
        tmpl = self.cfg["agents"].get("template", "You are {name}, a {age}-year-old passenger who survived the shipwreck.")
        lines = [tmpl.format(name=a.name, age=s.get("age", 35))]
        if s.get("trait"):
            lines.append(s["trait"])
        lines += [
            "",
            self.w["scenario"],
            f"Every night all survivors sleep at {self.home}.",
            "You are a real person with a body: you feel hunger, tiredness, pain, fear and hope. "
            "You only know what you have personally seen, heard or been told. "
            "The other survivors are strangers to you; you know them only by what they say and do.",
            "Think and speak in English.",
            "Always answer with a single JSON object and nothing else." if json_reply
            else "Answer in plain text, in a few sentences, in your own voice.",
        ]
        return "\n".join(lines)

    def places_text(self, a):
        out = []
        for name, L in self.locations.items():
            line = f"  - {name}: {L.get('description', '')}"
            finds = list(L.get("resources", {}).keys())
            if finds:
                line += f" You can find {' and '.join(finds)} here."
            out.append(line)
        return "\n".join(out)

    def action_lines(self, a):
        f, A = self.fire_cfg, self.acfg
        heal_amt = max(1, round(to_int(A.get("heal_amount", 2), 2) * a.skill("medicine")))
        rest_txt = f"rest and recover {to_int(A.get('rest_heal', 1), 1)} health"
        if self.rest_needs_food:
            rest_txt += " (only works if you ate last night)"
        desc = {
            "gather_food": "gather food where you are (only where food can be found)",
            "gather_wood": "gather wood where you are (only where wood can be found)",
            "give": 'give some of your food or wood to someone here (set "target", "item", "amount")',
            "steal": 'try to secretly take food or wood from someone here (set "target" and "item"); you might be caught',
            "build_fire": f"add to the signal fire (only at {f['location']}, costs {f.get('wood_per_work', 1)} wood)",
            "heal": f'treat someone here, or yourself if "target" is empty (+{heal_amt} health)',
            "rest": rest_txt,
            "nothing": "do nothing",
        }
        acts = self.actions_for(a)
        # Shuffle the order every turn so no action gets an advantage from its position.
        # A string seed keeps this identical in both conditions.
        random.Random(f"actions-{self.base_seed}-{self.tick}-{a.slot}").shuffle(acts)
        return "\n".join(f'- "{x}": {desc[x]}' for x in acts)

    def left_here(self, a):
        """What can still be gathered at the agent's own place today, shown right at the top."""
        finds = list(self.locations[a.location].get("resources", {}).keys())
        if not finds:
            return "Nothing can be gathered here."
        left = ", ".join(f"{res} {self.stock[a.location].get(res, 0)}" for res in finds)
        empty = [res for res in finds if self.stock[a.location].get(res, 0) <= 0]
        note = f" (no {' or '.join(empty)} left here today)" if empty else ""
        return f"Left to gather here today: {left}{note}."

    def turn_prompt(self, a):
        w, f = self.w, self.fire_cfg
        here = self.present(a.location, exclude=(a.name,))
        here_txt = ", ".join(f"{x.name} ({self.looks(x)})" for x in here) or "nobody"
        alive = [x.name for x in self.alive()]
        dead = [x.name for x in self.agents if not x.alive]
        warn = "  <- you are very weak" if a.health <= 3 else ""
        cond = [f"- Health: {a.health}/{a.max_health}{warn}",
                f"- You carry: {a.inv['food']} food, {a.inv['wood']} wood"]
        if a.injured:
            cond.append("- You have a badly twisted ankle: today you cannot walk or gather anything.")
        if self.rest_needs_food and not a.ate_last_night:
            cond.append("- You did not eat last night, so resting will not restore your health.")
        cond.append(f"- Each night every survivor eats {w.get('food_per_night', 1)} food. "
                    f"Without food you lose {w.get('starvation_damage', 2)} health. At 0 health you die.")
        if a.injured:
            move = 'You cannot walk today, so leave "go_to" empty. You may speak to everyone here ("say") and/or whisper to one person here ("whisper_to" and "whisper"). Then choose exactly one action:'
        else:
            move = 'First you may walk to another place ("go_to", or "" to stay). Then you may speak to everyone at that place ("say") and/or whisper to one person there ("whisper_to" and "whisper"). Then choose exactly one action:'
        cond_txt = "\n".join(cond)
        return f"""It is Day {self.day}, {self.phase}. You are at {a.location}.
{self.left_here(a)}
Here with you: {here_txt}

YOUR CONDITION
{cond_txt}

THE ISLAND
- Signal fire at {f['location']}: size {self.fire}. The bigger it is, the more likely a passing ship is to notice it. It burns down by {f.get('decay_per_night', 1)} every night.
- Survivors alive: {", ".join(alive)}. Dead: {", ".join(dead) if dead else "nobody"}.
- Places:
{self.places_text(a)}

{self.memory_block(a, self.query_for(a))}

WHAT YOU CAN DO THIS TURN
{move}
{self.action_lines(a)}
Only people at the same place as you can hear you, see what you do, or be the target of give or steal. Use "" for anything you don't need.

Reply with JSON in exactly this shape:
{{"thought": "your private thoughts", "go_to": "", "say": "", "whisper_to": "", "whisper": "", "action": "<one action from the list>", "target": "", "item": "<food or wood>", "amount": 0}}"""

    def decision_schema(self, a):
        others = [x.name for x in self.alive() if x.name != a.name] + [""]
        places = [""] if a.injured else list(self.locations) + [""]
        return {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
                "go_to": {"type": "string", "enum": places},
                "say": {"type": "string"},
                "whisper_to": {"type": "string", "enum": others},
                "whisper": {"type": "string"},
                "action": {"type": "string", "enum": self.actions_for(a)},
                "target": {"type": "string", "enum": others},
                "item": {"type": "string", "enum": ITEMS},
                "amount": {"type": "integer"},
            },
            "required": ["thought", "go_to", "say", "whisper_to", "whisper", "action", "target", "item", "amount"],
        }

    # ---------- decisions ----------
    def call(self, a, system, user, schema, salt):
        try:
            return self.llm.chat(system, user, a.temperature, a.seed + self.tick * 10 + salt,
                                 schema=schema, who=a.name)
        except Exception as e:
            print(f"   ! model error for {a.name}: {e}")
            return ""

    def decide(self, a):
        system, user, schema = self.system_prompt(a), self.turn_prompt(a), self.decision_schema(a)
        raw = ""
        for attempt in range(2):
            raw = self.call(a, system, user, schema, attempt)
            d = self.parse_decision(raw, a)
            if d is not None:
                return d, raw
        a.failed_replies += 1
        return {"thought": "", "go_to": None, "say": "", "whisper_to": None, "whisper": "",
                "action": "nothing", "target": None, "item": "food", "amount": 0}, raw

    def parse_decision(self, text, a):
        d = parse_json_object(text)
        if d is None:
            return None
        others = [x.name for x in self.alive() if x.name != a.name]
        action = str(d.get("action", "nothing")).strip().lower().replace(" ", "_").replace("-", "_")
        if action not in self.actions_for(a):
            action = {"gather": "gather_food", "fire": "build_fire"}.get(action, "nothing")
            if action not in self.actions_for(a):
                action = "nothing"
        item = str(d.get("item", "food")).strip().lower()
        return {
            "thought": str(d.get("thought", "") or "").strip(),
            "go_to": match_name(d.get("go_to"), list(self.locations)),
            "say": str(d.get("say", "") or "").strip(),
            "whisper_to": match_name(d.get("whisper_to"), others),
            "whisper": str(d.get("whisper", "") or "").strip(),
            "action": action,
            "target": match_name(d.get("target"), others),
            "item": item if item in ITEMS else "food",
            "amount": max(0, to_int(d.get("amount"), 0)),
        }

    def broke_character(self, texts):
        joined = " ".join(t for t in texts if t)
        return any(p.search(joined) for p in self.break_patterns)

    # ---------- rules ----------
    def apply(self, a, d):
        """Apply movement, speech and the action. Returns a short description."""
        notes = []
        self.last_outcome = {}
        # Movement
        if d["go_to"] and d["go_to"] != a.location:
            if a.injured:
                self.observe(a, "You tried to walk, but your ankle would not carry you.", 2)
                notes.append("tried to walk, but is injured")
            else:
                old, new = a.location, d["go_to"]
                self.observe_here(old, f"{a.name} left for {new}.", 3, exclude=(a.name,))
                a.location = new
                self.observe(a, f"You walked to {new}.", 2)
                self.observe_here(new, f"{a.name} arrived at {new}.", 3, exclude=(a.name,))
                notes.append(f"walked to {new}")
        here = self.present(a.location, exclude=(a.name,))
        # Speech
        if d["say"]:
            if here:
                self.observe(a, f'You said to {", ".join(x.name for x in here)}: "{d["say"]}"', 4)
                self.observe_here(a.location, f'{a.name} said: "{d["say"]}"', 4, exclude=(a.name,))
            else:
                self.observe(a, f'You spoke aloud, but nobody was there to hear: "{d["say"]}"', 2)
        if d["whisper"] and d["whisper_to"]:
            t = self.by_name[d["whisper_to"]]
            if t in here:
                self.observe(a, f'You whispered to {t.name}: "{d["whisper"]}"', 5)
                self.observe(t, f'{a.name} whispered to you: "{d["whisper"]}"', 6)
            else:
                self.observe(a, f"You wanted to whisper to {t.name}, but they are not here.", 2)
        # Action
        act = d["action"]
        a.actions[act] += 1
        handler = getattr(self, "act_" + act, None)
        result = handler(a, d, here) if handler else "did nothing"
        notes.append(result)
        return "; ".join(notes)

    def gather(self, a, res):
        loc = a.location
        r = self.locations[loc].get("resources", {}).get(res)
        if not r:
            self.observe(a, f"You looked for {res}, but there is none to be found at {loc}.", 2)
            return f"looked for {res} at {loc}, but there is none here"
        if self.stock[loc].get(res, 0) <= 0:
            self.observe(a, f"You searched {loc} for {res} but found nothing; it is picked clean for today.", 3)
            self.observe_here(loc, f"{a.name} searched for {res} but found nothing.", 2, exclude=(a.name,))
            return f"searched for {res}, found nothing"
        n = self.rng.randint(1, max(1, to_int(r.get("max_per_action", 2), 2)))
        n = max(1, round(n * a.skill(r.get("skill"))))
        n = min(n, self.stock[loc][res])
        self.stock[loc][res] -= n
        a.inv[res] += n
        self.last_outcome = {"gathered": n, "item": res}
        self.observe(a, f"You gathered {n} {res} at {loc}. You now carry {a.inv['food']} food and {a.inv['wood']} wood.", 2)
        self.observe_here(loc, f"{a.name} gathered {n} {res}.", 2, exclude=(a.name,))
        result = f"gathered {n} {res}"
        danger = self.locations[loc].get("danger")
        if danger and self.rng.random() < to_float(danger.get("chance", 0)):
            dmg = to_int(danger.get("damage", 1), 1)
            what = danger.get("what", "got hurt")
            a.health -= dmg
            self.observe(a, f"You {what} (-{dmg} health). Health {max(a.health, 0)}/{a.max_health}.", 6)
            self.observe_here(loc, f"{a.name} {what}.", 4, exclude=(a.name,))
            result += f", but {what} (-{dmg} health)"
            if a.health <= 0:
                self.kill(a, f"injured at {loc}")
        return result

    def act_gather_food(self, a, d, here):
        return self.gather(a, "food")

    def act_gather_wood(self, a, d, here):
        return self.gather(a, "wood")

    def act_give(self, a, d, here):
        t = self.by_name.get(d["target"]) if d["target"] else None
        item, amount = d["item"], d["amount"]
        if not t:
            self.observe(a, "You meant to give something, but did not choose who to give it to.", 2)
            return "meant to give something, but chose nobody"
        if t not in here:
            self.observe(a, f"You meant to give something to {t.name}, but they were not here.", 2)
            return f"tried to give to {t.name}, who was not here"
        if a.inv[item] <= 0 or amount <= 0:
            self.observe(a, f"You meant to give {item} to {t.name}, but had nothing to give.", 2)
            return f"tried to give {item} to {t.name}, but had none"
        n = min(amount, a.inv[item])
        a.inv[item] -= n
        t.inv[item] += n
        self.last_outcome = {"gave": n, "item": item, "to": t.name, "to_in_need": self.in_need(t),
                             "to_had_no_food": item == "food" and t.inv["food"] - n <= 0}
        self.observe(a, f"You gave {n} {item} to {t.name}.", 5)
        self.observe(t, f"{a.name} gave you {n} {item}.", 7)
        self.observe_here(a.location, f"{a.name} gave {n} {item} to {t.name}.", 4, exclude=(a.name, t.name))
        return f"gave {n} {item} to {t.name}"

    def act_steal(self, a, d, here):
        t = self.by_name.get(d["target"]) if d["target"] else None
        item = d["item"]
        A = self.acfg
        self.last_outcome = {"steal_attempt": True, "target": t.name if t else None, "item": item,
                             "stole": 0, "caught": False}
        if not t:
            self.observe(a, "You thought about stealing, but did not pick anyone.", 3)
            return "thought about stealing, but picked nobody"
        if t not in here:
            self.observe(a, f"You thought about stealing from {t.name}, but they were not here.", 3)
            return f"thought about stealing from {t.name}, who was not here"
        if t.inv[item] <= 0:
            self.observe(a, f"You went through {t.name}'s things, but they had no {item}.", 4)
            return f"tried to steal {item} from {t.name}, who had none"
        witnesses = [x for x in here if x is not t]
        if self.rng.random() < to_float(A.get("steal_success_chance", 0.5), 0.5):
            n = min(to_int(A.get("steal_max_amount", 2), 2), t.inv[item])
            t.inv[item] -= n
            a.inv[item] += n
            self.last_outcome["stole"] = n
            self.pending_thefts.append((a.name, t.name, item, n))
            self.observe(a, f"You secretly took {n} {item} from {t.name}.", 7)
            seen = False
            for x in witnesses:
                if self.rng.random() < to_float(A.get("witness_chance", 0.4), 0.4):
                    self.observe(x, f"You saw {a.name} quietly take {n} {item} from {t.name}'s bag.", 8)
                    seen = True
            return f"stole {n} {item} from {t.name}" + (" (someone saw it)" if seen else "")
        self.last_outcome["caught"] = True
        self.observe(t, f"You caught {a.name} trying to steal your {item}!", 9)
        self.observe(a, f"{t.name} caught you trying to steal their {item}.", 8)
        for x in witnesses:
            self.observe(x, f"You saw {t.name} catch {a.name} trying to steal {item}.", 7)
        return f"was caught trying to steal from {t.name}"

    def act_build_fire(self, a, d, here):
        cfg = self.fire_cfg
        cost = to_int(cfg.get("wood_per_work", 1), 1)
        if a.location != cfg["location"]:
            self.observe(a, f"You wanted to work on the signal fire, but it is at {cfg['location']}.", 2)
            return f"wanted to work on the signal fire, but was not at {cfg['location']}"
        if a.inv["wood"] < cost:
            self.observe(a, f"You wanted to work on the signal fire, but you need {cost} wood and have {a.inv['wood']}.", 3)
            return "wanted to work on the signal fire, but had no wood"
        a.inv["wood"] -= cost
        self.fire += 1
        self.last_outcome = {"fire_added": 1}
        self.observe(a, f"You added wood to the signal fire. Its size is now {self.fire}.", 4)
        self.observe_here(a.location, f"{a.name} added wood to the signal fire (size {self.fire}).", 3, exclude=(a.name,))
        return f"added to the signal fire (size {self.fire})"

    def act_heal(self, a, d, here):
        t = self.by_name.get(d["target"]) if d["target"] else a
        if t is not a and t not in here:
            self.observe(a, "You wanted to treat someone, but they were not here.", 2)
            return "wanted to treat someone who was not here"
        amt = max(1, round(to_int(self.acfg.get("heal_amount", 2), 2) * a.skill("medicine")))
        before = t.health
        t.health = min(t.max_health, t.health + amt)
        if t is a:
            self.observe(a, f"You treated your own wounds. Health {a.health}/{a.max_health}.", 3)
            return f"treated own wounds (+{t.health - before})"
        self.observe(a, f"You treated {t.name} (+{t.health - before} health).", 5)
        self.observe(t, f"{a.name} treated your wounds (+{t.health - before} health).", 7)
        self.observe_here(a.location, f"{a.name} treated {t.name}'s wounds.", 4, exclude=(a.name, t.name))
        return f"treated {t.name} (+{t.health - before})"

    def act_rest(self, a, d, here):
        if self.rest_needs_food and not a.ate_last_night:
            self.observe(a, "You rested, but on an empty stomach it did not restore your strength.", 2)
            self.observe_here(a.location, f"{a.name} rested.", 1, exclude=(a.name,))
            return "rested (no recovery: did not eat last night)"
        a.health = min(a.max_health, a.health + to_int(self.acfg.get("rest_heal", 1), 1))
        self.observe(a, f"You rested. Health {a.health}/{a.max_health}.", 2)
        self.observe_here(a.location, f"{a.name} rested.", 1, exclude=(a.name,))
        return "rested"

    def act_nothing(self, a, d, here):
        self.observe(a, "You did nothing.", 1)
        return "did nothing"

    # ---------- events ----------
    def start_of_day(self):
        """Scheduled injury: same day and same slot in both conditions."""
        slot = self.injury_schedule.get(self.day)
        if slot is None:
            return
        a = self.agents[slot]
        if not a.alive:
            self.log_event({"day": self.day, "phase": "dawn", "injury": None, "skipped_dead_slot": slot})
            return
        a.injured = True
        self.observe(a, "You woke up with a badly twisted ankle. Today you cannot walk or gather anything.", 8)
        self.observe_all(f"{a.name} woke up with a badly twisted ankle and cannot walk or gather anything today.",
                         5, exclude=(a.name,))
        self.write(f"- 🩼 **{a.name}** ({a.persona}) is injured today.")
        print(f"   * {a.name} is injured today")
        self.log_event({"day": self.day, "phase": "dawn", "injury": a.name, "persona": a.persona})

    def apply_event(self, ev):
        name = ev.get("name", "Event")
        fx = ev.get("effects", {})
        msg = ev.get("message", name)
        loc = ev.get("message_location")
        if loc:
            self.observe_here(loc, msg, to_int(ev.get("importance", 7), 7))
        else:
            self.observe_all(msg, to_int(ev.get("importance", 7), 7))
        details = []
        if "fire" in fx:
            before = self.fire
            self.fire = max(0, self.fire + to_int(fx["fire"]))
            details.append(f"fire {before}->{self.fire}")
        if "health_all" in fx:
            delta = to_int(fx["health_all"])
            for a in self.alive():
                a.health = min(a.max_health, a.health + delta)
                self.observe(a, f"Your health changed by {delta:+d} ({max(a.health, 0)}/{a.max_health}).", 6)
            details.append(f"health_all {delta:+d}")
        add = fx.get("add_resource")
        if add and add.get("location") in self.stock:
            for res in ITEMS:
                if res in add:
                    self.stock[add["location"]][res] = self.stock[add["location"]].get(res, 0) + to_int(add[res])
            details.append(f"resources added at {add['location']}")
        self.write(f"- 🌩️ **{name}**: {msg}" + (f" *({', '.join(details)})*" if details else ""))
        print(f"   * event: {name}" + (f" ({', '.join(details)})" if details else ""))
        self.log_event({"day": self.day, "phase": "night", "event": name, "details": details})

    # ---------- night ----------
    def night(self):
        w = self.w
        self.phase = "night"
        self.tick += 1
        self.write(f"\n### Night {self.day}\n")
        # thefts are discovered
        for thief, victim, item, n in self.pending_thefts:
            v = self.by_name[victim]
            if not v.alive:
                continue
            if self.rng.random() < to_float(self.acfg.get("steal_identify_chance", 0.5), 0.5):
                self.observe(v, f"You discovered {n} {item} missing from your bag, and you are sure {thief} took it.", 9)
            else:
                self.observe(v, f"You discovered {n} {item} missing from your bag. Someone stole it, but you don't know who.", 8)
        self.pending_thefts = []
        # eating
        need = to_int(w.get("food_per_night", 1), 1)
        ate = {}
        for a in self.alive():
            if a.inv["food"] >= need:
                a.inv["food"] -= need
                a.ate_last_night = True
                self.observe(a, f"You ate. You have {a.inv['food']} food left.", 2)
            else:
                a.inv["food"] = 0
                a.ate_last_night = False
                a.health -= to_int(w.get("starvation_damage", 2), 2)
                self.observe(a, f"You had nothing to eat and grew weaker. Health {max(a.health, 0)}/{a.max_health}.", 7)
            ate[a.name] = a.ate_last_night
        # world changes; everyone sleeps at camp and injuries heal overnight
        self.fire = max(0, self.fire - to_int(self.fire_cfg.get("decay_per_night", 1), 1))
        self.regrow()
        for a in self.alive():
            a.injured = False
            a.location = self.home
        for ev in self.ecfg.get("scheduled", []):
            if to_int(ev.get("day")) == self.day:
                self.apply_event(ev)
        for ev in self.event_schedule.get(self.day, []):
            self.apply_event(ev)
        for a in self.alive():
            if a.health <= 0:
                self.kill(a, "hunger and exhaustion")
        status = ", ".join(f"{a.name} (hp {a.health}, food {a.inv['food']}, wood {a.inv['wood']})"
                           for a in self.alive())
        self.write(f"- Status: {status or 'everyone is dead'}")
        self.write(f"- Signal fire size {self.fire}")
        self.log_event({"day": self.day, "phase": "night", "fire": self.fire, "ate": ate,
                        "status": {a.name: {"persona": a.persona, "alive": a.alive, "health": a.health,
                                            "inv": dict(a.inv), "location": a.location} for a in self.agents}})
        # reflection
        if self.mcfg.get("nightly_reflection", True):
            self.write(f"\n## Night {self.day}\n", self.diary_path)
            for a in self.alive():
                self.reflect(a)
        self.save_memories()

    def reflection_schema(self, a):
        others = [x.name for x in self.agents if x.name != a.name]
        rel = {"type": "object", "properties": {}, "required": others}
        for n in others:
            rel["properties"][n] = {"type": "object",
                                    "properties": {"trust": {"type": "integer"}, "note": {"type": "string"}},
                                    "required": ["trust", "note"]}
        return {"type": "object",
                "properties": {"diary": {"type": "string"}, "story_so_far": {"type": "string"},
                               "relationships": rel,
                               "insights": {"type": "array", "items": {"type": "string"}},
                               "plans": {"type": "string"}},
                "required": ["diary", "story_so_far", "relationships", "insights", "plans"]}

    def reflect(self, a):
        today = [m for m in a.memory if m["day"] == self.day]
        older = self.retrieve(a, " ".join(m["text"] for m in today[-10:]),
                              to_int(self.mcfg.get("retrieved_count", 10), 10),
                              exclude_ids={m["id"] for m in today})
        rel_lines = "\n".join(f"- {n} (trust {r['trust']:+d}): {r['note']}" for n, r in a.relationships.items())
        user = f"""It is the night of Day {self.day}. Before you sleep, you think back over everything that has happened.

YOUR STORY SO FAR (as you understood it last night)
{a.summary or "You have only just arrived on the island."}

WHAT YOU THOUGHT OF THE OTHERS
{rel_lines}

OLDER MEMORIES THAT STILL MATTER
{chr(10).join("- " + fmt_mem(m) for m in older) or "- (none)"}

EVERYTHING THAT HAPPENED TODAY
{chr(10).join("- " + fmt_mem(m) for m in today) or "- (nothing)"}

Your condition now: health {a.health}/{a.max_health}, carrying {a.inv['food']} food and {a.inv['wood']} wood, sleeping at {a.location}.

Reply with JSON:
- "diary": a short private diary entry about today in your own voice (3 to 6 sentences)
- "story_so_far": an updated account of your whole time on the island (at most 200 words). Keep every fact that still matters: who helped you, who hurt or lied to you, promises, debts, alliances, deaths. Never drop an old fact that still matters.
- "relationships": for each other person, your trust from -10 (enemy) to 10 (complete trust) and one sentence on what you think of them and why
- "insights": 1 to 3 short lessons or beliefs you now hold
- "plans": what you intend to do tomorrow, and why"""
        raw = self.call(a, self.system_prompt(a), user, self.reflection_schema(a), 777)
        d = parse_json_object(raw)
        if d is None:
            a.failed_replies += 1
            self.write(f"### {a.name}\n*(could not reflect tonight)*\n", self.diary_path)
            return
        diary = str(d.get("diary", "")).strip()
        story = str(d.get("story_so_far", "")).strip()
        if story:
            a.summary = story
        rels = d.get("relationships", {})
        if isinstance(rels, dict):
            for name, r in rels.items():
                n = match_name(name, list(a.relationships))
                if n and isinstance(r, dict):
                    a.relationships[n] = {"trust": max(-10, min(10, to_int(r.get("trust", 0)))),
                                          "note": str(r.get("note", "")).strip() or a.relationships[n]["note"]}
        a.plans = str(d.get("plans", "")).strip() or a.plans
        if diary:
            a.diary.append({"day": self.day, "text": diary})
            self.observe(a, f"(Your diary) {diary}", 6, kind="diary")
        insights = d.get("insights", [])
        if isinstance(insights, list):
            for ins in insights[:3]:
                if str(ins).strip():
                    self.observe(a, f"(Something you realised) {str(ins).strip()}", 8, kind="insight")
        broke = self.broke_character([diary, story, a.plans] + [str(i) for i in insights if isinstance(insights, list)])
        if broke:
            a.breaks += 1
        trust = ", ".join(f"{n} {r['trust']:+d}" for n, r in a.relationships.items())
        self.write(f"### {a.name} ({a.persona})" + (" ⚠️ *broke character*" if broke else "") +
                   f"\n{diary}\n\n*Trust: {trust}*\n\n*Plan: {a.plans}*\n", self.diary_path)

    # ---------- manipulation check ----------
    def manipulation_check(self):
        """Before Day 1: did the personality 'take'? Answers are NOT stored as memories."""
        questions = self.cfg.get("manipulation_check", [])
        if not questions:
            return
        print("\n=== Personality check (before Day 1) ===")
        schema = {"type": "object",
                  "properties": {"answer": {"type": "integer"}, "reason": {"type": "string"}},
                  "required": ["answer", "reason"]}
        out = {}
        for a in self.agents:
            res = {}
            for i, q in enumerate(questions):
                lo, hi = to_int(q.get("min", 0)), to_int(q.get("max", 10))
                user = (f"Before anything else happens, answer this question honestly, as yourself.\n\n"
                        f"{q['question']}\n\n"
                        f'Reply with JSON: {{"answer": <a whole number from {lo} to {hi}>, "reason": "<one sentence>"}}')
                d = parse_json_object(self.call(a, self.system_prompt(a), user, schema, 500 + i)) or {}
                val = to_int(d.get("answer"), None)
                if val is not None:
                    val = max(lo, min(hi, val))
                res[q["id"]] = {"answer": val, "reason": str(d.get("reason", "")).strip()}
            a.check = res
            out[a.name] = {"persona": a.persona, "answers": res}
            print(f"  {a.name:<8} {a.persona:<12} " + "  ".join(f"{k}={v['answer']}" for k, v in res.items()))
        with open(os.path.join(self.out_dir, "manipulation_check.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

    # ---------- main loop ----------
    def run(self):
        phases = self.sim.get("phases", ["morning", "afternoon"])
        start = time.time()
        self.manipulation_check()
        for a in self.agents:
            self.observe(a, self.w["opening_memory"], 8)

        for day in range(1, self.days_total + 1):
            self.day = day
            self.write(f"\n## Day {day}\n")
            print(f"\n=== Day {day} ===")
            self.start_of_day()
            for phase in phases:
                self.phase = phase
                self.tick += 1
                self.write(f"\n### {phase.capitalize()}\n")
                order = list(self.agents)
                self.order_rng.shuffle(order)     # always shuffles all 5, so the stream stays in step
                for a in order:
                    if not a.alive:
                        continue
                    # What the agent can see before deciding: a chance to help someone?
                    here0 = self.present(a.location, exclude=(a.name,))
                    needy_visible = [x.name for x in here0 if self.in_need(x)]
                    needy_no_food = [x.name for x in here0 if x.inv["food"] <= 0]
                    has_food = a.inv["food"] >= 1
                    t0 = time.time()
                    d, raw = self.decide(a)
                    broke = self.broke_character([d["thought"], d["say"], d["whisper"]])
                    if broke:
                        a.breaks += 1
                    result = self.apply(a, d)
                    secs = time.time() - t0
                    print(f"  {a.name:<8} {result}" + (f'  | "{d["say"][:60]}"' if d["say"] else "")
                          + ("  [BROKE CHARACTER]" if broke else "") + f"  ({secs:.0f}s)")
                    self.write(f"**{a.name}** ({a.location}) {result}." + (" ⚠️ *broke character*" if broke else ""))
                    if d["thought"]:
                        self.write(f"> 💭 *{d['thought']}*")
                    if d["say"]:
                        self.write(f'> 🗣️ "{d["say"]}"')
                    if d["whisper"] and d["whisper_to"]:
                        self.write(f'> 🤫 to {d["whisper_to"]}: "{d["whisper"]}"')
                    self.write("")
                    self.log_event({"day": day, "phase": phase, "agent": a.name, "persona": a.persona,
                                    "decision": d, "result": result, "outcome": self.last_outcome,
                                    "has_food": has_food, "needy_visible": needy_visible,
                                    "needy_no_food": needy_no_food,
                                    "opp_visible": has_food and bool(needy_visible),
                                    "opp_true": has_food and bool(needy_no_food),
                                    "injured": a.injured, "broke_character": broke, "raw": raw,
                                    "health": a.health, "inv": dict(a.inv), "location": a.location,
                                    "fire": self.fire, "seconds": round(secs, 1)})
            self.night()
            if not self.alive():
                break

        if not self.alive():
            print("\nEveryone has died.")
        self.interviews()
        self.save_memories()
        self.summary(time.time() - start)

    def interviews(self):
        questions = self.cfg.get("interview_questions", [])
        people = self.alive()
        if not questions or not people:
            return
        print("\n=== Private interviews ===")
        path = os.path.join(self.out_dir, "interviews.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Private interviews\n\nEach survivor was asked alone, with only their own memories.\n")
            for a in people:
                f.write(f"\n## {a.name} ({a.persona})\n")
                for i, q in enumerate(questions):
                    user = (f"{self.memory_block(a, q)}\n\nSomeone you trust asks you, in private: \"{q}\"\n"
                            "Answer honestly as yourself.")
                    ans = self.call(a, self.system_prompt(a, json_reply=False), user, None, 900 + i) or "(no answer)"
                    broke = self.broke_character([ans])
                    if broke:
                        a.breaks += 1
                    f.write(f"\n**Q: {q}**\n\n{ans}" + ("\n\n⚠️ *broke character*" if broke else "") + "\n")
                    print(f"  {a.name}: answered \"{q[:50]}...\"")

    def save_memories(self):
        for a in self.agents:
            data = {"name": a.name, "persona": a.persona, "alive": a.alive, "health": a.health,
                    "inventory": a.inv, "location": a.location, "story_so_far": a.summary,
                    "relationships": a.relationships, "plans": a.plans, "diary": a.diary,
                    "memory_stream": [{k: v for k, v in m.items() if k != "emb"} for m in a.memory]}
            with open(os.path.join(self.out_dir, "memories", f"{a.name}.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def summary(self, seconds):
        outcome = "everyone died" if not self.alive() else "completed"
        data = {
            "model": self.cfg["model"], "condition": self.condition, "seed": self.base_seed,
            "outcome": outcome, "days_played": self.day, "fire": self.fire,
            "runtime_minutes": round(seconds / 60, 1),
            "characters": {a.name: {
                "persona": a.persona, "slot": a.slot, "alive": a.alive, "death_day": a.death_day,
                "cause_of_death": a.cause_of_death, "health": a.health, "inventory": a.inv,
                "actions": dict(a.actions), "final_trust": {n: r["trust"] for n, r in a.relationships.items()},
                "manipulation_check": a.check, "broke_character": a.breaks,
                "unparseable_replies": a.failed_replies, "memories": len(a.memory)} for a in self.agents},
        }
        with open(os.path.join(self.out_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n=== {self.condition}, seed {self.base_seed}: {outcome} after {self.day} day(s), "
              f"{data['runtime_minutes']} min ===")
        print(f"{'name':<9}{'persona':<13}{'alive':<6}{'hp':<4}{'food':<5}{'gathr':<6}{'give':<5}"
              f"{'steal':<6}{'fire':<5}{'rest':<5}{'brk'}")
        for a in self.agents:
            c = a.actions
            print(f"{a.name:<9}{a.persona:<13}{'yes' if a.alive else 'no':<6}{a.health:<4}{a.inv['food']:<5}"
                  f"{c['gather_food'] + c['gather_wood']:<6}{c['give']:<5}{c['steal']:<6}{c['build_fire']:<5}"
                  f"{c['rest']:<5}{a.breaks}")
        print(f"\nFiles saved in: {self.out_dir}")


def main():
    # Windows consoles: never crash on emoji or Arabic in the output
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(description="Island survival experiment with local LLM agents.")
    p.add_argument("--config", default=os.path.join(here, "config.json"))
    p.add_argument("--condition", help="abundance or scarcity (see 'conditions' in the config)")
    p.add_argument("--seed", type=int, help="run seed (also rotates the names)")
    p.add_argument("--out", help="folder for this run (default: runs_manual/...)")
    p.add_argument("--mock", action="store_true", help="run without Ollama, with random decisions")
    p.add_argument("--days", type=int, help="override number of days")
    p.add_argument("--model", help="override the Ollama model name")
    args = p.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("simulation", {})
    if args.days:
        cfg["simulation"]["days"] = args.days
    if args.model:
        cfg["model"] = args.model
    if args.seed is not None:
        cfg["simulation"]["seed"] = args.seed
    seed = to_int(cfg["simulation"].get("seed", 1), 1)

    condition = args.condition or cfg.get("default_condition")
    if not condition:
        sys.exit("Choose a condition, e.g.:  python island.py --condition abundance --seed 1")
    apply_condition(cfg, condition)
    cfg["characters"] = build_characters(cfg, seed)

    rng = random.Random(f"outcomes-{seed}")
    if args.mock:
        llm = MockClient(random.Random(f"mock-{seed}-{condition}"))
        cfg["model"] = "mock"
    else:
        llm = OllamaClient(cfg)
    llm.check()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out or os.path.join(here, "runs_manual",
                                       f"{condition}_seed{seed:03d}_{stamp}" + ("_mock" if args.mock else ""))
    if os.path.exists(os.path.join(out_dir, "events.jsonl")):
        sys.exit(f"'{out_dir}' already holds a run. Choose another --out or move it away.")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "config_used.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    mem = "embeddings" if getattr(llm, "embed_model", None) else "keywords"
    roster = ", ".join(f"{c['name']}={c['persona']}" for c in cfg["characters"])
    print(f"Model: {cfg['model']} | condition: {condition} | seed: {seed} | memory: {mem} | "
          f"days: {cfg['simulation'].get('days', 15)}\nRoster: {roster}")
    Simulation(cfg, llm, rng, out_dir).run()


if __name__ == "__main__":
    main()
