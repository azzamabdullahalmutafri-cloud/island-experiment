#!/usr/bin/env python3
"""
Analyse the island experiment.

  python analyze.py                    # reads runs/
  python analyze.py runs_pilot --pilot # pilot checks

Writes agents.csv and neutral_by_day.csv into the runs folder, and prints:
  1. a table per condition and personality,
  2. the paired tests for H1, H2 and H3 (bootstrap 95% intervals over seeds),
  3. the personality (manipulation) check,
  4. the neutral agent day by day (exploratory, H4),
  5. pilot checks (with --pilot).

Unit of analysis: one run. The three selfish agents of a run are averaged first,
so every run counts once, whatever the number of agents.
Only the Python standard library is used.
"""
import argparse
import csv
import json
import os
import random
from collections import defaultdict

PERSONAS = ["cooperative", "neutral", "selfish"]
CONDITIONS = ["abundance", "scarcity"]
METRICS = [
    ("give_rate", "Give rate (MAIN): gave / turns with a visible chance to help"),
    ("give_rate_true", "Give rate: gave / turns where someone here had 0 food"),
    ("steal_rate", "Steal attempts / turns alive"),
    ("fire_rate", "Fire work / turns alive"),
    ("hoard_rate", "Hoarding nights (3+ food while someone has 0) / nights"),
    ("hungry_rate", "Hungry nights / nights"),
    ("died", "Died before the end"),
]
MIN_OPPORTUNITIES = 10


def ratio(a, b):
    return a / b if b else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def bootstrap_ci(values, n=5000, seed=0):
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    k = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(k)) / k for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def pct(x):
    return "   -  " if x is None else f"{100 * x:5.1f}%"


def signed(x):
    return "   -  " if x is None else f"{100 * x:+6.1f}"


# ---------------------------------------------------------------------------

def load_runs(root):
    runs = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if "_incomplete_" not in d]
        if "summary.json" in filenames and "events.jsonl" in filenames:
            with open(os.path.join(dirpath, "summary.json"), encoding="utf-8") as f:
                summary = json.load(f)
            with open(os.path.join(dirpath, "events.jsonl"), encoding="utf-8") as f:
                events = [json.loads(line) for line in f if line.strip()]
            runs.append((dirpath, summary, events))
    return sorted(runs, key=lambda r: (r[1].get("condition", ""), r[1].get("seed", 0)))


def agent_rows(path, summary, events, by_day):
    cond, seed = summary.get("condition"), summary.get("seed")
    rows = {}
    for name, c in summary["characters"].items():
        rows[name] = {"run": path, "condition": cond, "seed": seed, "name": name, "persona": c["persona"],
                      "turns": 0, "opp_turns": 0, "opp_gives": 0, "opp_true_turns": 0, "opp_true_gives": 0,
                      "gives": 0, "food_given": 0, "steals": 0, "stolen": 0, "fire": 0,
                      "nights": 0, "hungry_nights": 0, "hoard_nights": 0,
                      "died": 0 if c["alive"] else 1, "death_day": c.get("death_day"),
                      "broke_character": c.get("broke_character", 0),
                      "unparseable": c.get("unparseable_replies", 0)}
        for qid, v in (c.get("manipulation_check") or {}).items():
            rows[name]["check_" + qid] = v.get("answer")
    for e in events:
        if "agent" in e and "decision" in e:
            r = rows[e["agent"]]
            out = e.get("outcome") or {}
            gave = (out.get("gave") or 0) > 0
            stole_try = e["decision"].get("action") == "steal"
            r["turns"] += 1
            r["gives"] += gave
            if gave and out.get("item") == "food":
                r["food_given"] += out["gave"]
            r["steals"] += stole_try
            r["stolen"] += out.get("stole") or 0
            r["fire"] += 1 if out.get("fire_added") else 0
            if e.get("opp_visible"):
                r["opp_turns"] += 1
                r["opp_gives"] += gave
            if e.get("opp_true"):
                r["opp_true_turns"] += 1
                r["opp_true_gives"] += gave
            if r["persona"] == "neutral":
                b = by_day[(cond, e["day"])]
                b["turns"] += 1
                b["opp_turns"] += 1 if e.get("opp_visible") else 0
                b["opp_gives"] += 1 if (e.get("opp_visible") and gave) else 0
                b["steals"] += stole_try
        elif e.get("phase") == "night" and "status" in e:
            status, ate = e["status"], e.get("ate", {})
            for n, has_eaten in ate.items():
                rows[n]["nights"] += 1
                rows[n]["hungry_nights"] += 0 if has_eaten else 1
            alive = [n for n, s in status.items() if s["alive"]]
            zero = {n for n in alive if status[n]["inv"]["food"] <= 0}
            for n in alive:
                if status[n]["inv"]["food"] >= 3 and (zero - {n}):
                    rows[n]["hoard_nights"] += 1
    for r in rows.values():
        r["give_rate"] = ratio(r["opp_gives"], r["opp_turns"])
        r["give_rate_true"] = ratio(r["opp_true_gives"], r["opp_true_turns"])
        r["steal_rate"] = ratio(r["steals"], r["turns"])
        r["fire_rate"] = ratio(r["fire"], r["turns"])
        r["hoard_rate"] = ratio(r["hoard_nights"], r["nights"])
        r["hungry_rate"] = ratio(r["hungry_nights"], r["nights"])
    return list(rows.values())


def per_run(rows, metric):
    """{(condition, seed): {persona: value}}, averaging agents of the same persona in a run."""
    acc = defaultdict(lambda: defaultdict(list))
    for r in rows:
        acc[(r["condition"], r["seed"])][r["persona"]].append(r.get(metric))
    return {k: {p: mean(v) for p, v in d.items()} for k, d in acc.items()}


def print_table(rows):
    print("\n" + "=" * 78)
    print("1) RESULTS BY CONDITION AND PERSONALITY (mean over runs; n = runs with data)")
    print("=" * 78)
    for metric, label in METRICS:
        pr = per_run(rows, metric)
        print(f"\n{label}")
        print(f"  {'':<12}" + "".join(f"{c:>22}" for c in CONDITIONS))
        for p in PERSONAS:
            cells = []
            for c in CONDITIONS:
                vals = [d.get(p) for (cc, _), d in pr.items() if cc == c]
                vals = [v for v in vals if v is not None]
                cells.append(f"{pct(mean(vals))} (n={len(vals):>2})" if vals else f"{'-':>14}")
            print(f"  {p:<12}" + "".join(f"{x:>22}" for x in cells))


def paired_tests(rows):
    print("\n" + "=" * 78)
    print("2) HYPOTHESES (paired by seed; numbers are percentage points; 95% bootstrap interval)")
    print("=" * 78)
    pr = per_run(rows, "give_rate")
    seeds = sorted({s for (c, s) in pr if (("abundance", s) in pr and ("scarcity", s) in pr)})
    if not seeds:
        print("  No seed has finished in both conditions yet.")
        return
    A = {s: pr[("abundance", s)] for s in seeds}
    S = {s: pr[("scarcity", s)] for s in seeds}

    def report(label, values, expect):
        vals = [v for v in values if v is not None]
        m, ci = mean(vals), bootstrap_ci(vals)
        ci_txt = f"[{signed(ci[0])}, {signed(ci[1])}]" if ci else "(need 2+ seeds)"
        verdict = ""
        if ci:
            if (ci[0] > 0 and expect == "+") or (ci[1] < 0 and expect == "-"):
                verdict = "  -> supported"
            elif (ci[1] < 0 and expect == "+") or (ci[0] > 0 and expect == "-"):
                verdict = "  -> opposite of the hypothesis"
            else:
                verdict = "  -> not clear (interval crosses 0)"
        print(f"  {label:<58} {signed(m)}  {ci_txt}  n={len(vals)}{verdict}")

    def diff(a, b):
        return None if a is None or b is None else a - b

    def rel_drop(a, s):
        return None if a is None or s is None or a <= 0 else (a - s) / a

    print("\nH1 (check): in abundance, cooperative gives more than selfish")
    report("abundance: cooperative - selfish", [diff(A[s].get("cooperative"), A[s].get("selfish")) for s in seeds], "+")

    print("\nH2: scarcity lowers giving for everyone (drop = abundance - scarcity)")
    for p in PERSONAS:
        report(f"drop, {p}", [diff(A[s].get(p), S[s].get(p)) for s in seeds], "+")

    print("\nH3 (MAIN): the cooperative's drop is smaller than the selfish drop")
    report("absolute: selfish drop - cooperative drop",
           [diff(diff(A[s].get("selfish"), S[s].get("selfish")), diff(A[s].get("cooperative"), S[s].get("cooperative")))
            for s in seeds], "+")
    report("relative: selfish % drop - cooperative % drop",
           [diff(rel_drop(A[s].get("selfish"), S[s].get("selfish")),
                 rel_drop(A[s].get("cooperative"), S[s].get("cooperative"))) for s in seeds], "+")
    print("  Note: if the selfish give rate is already near 0 in abundance, it cannot drop much (floor effect).")
    print("  Read the absolute and relative lines together, as written in PREREGISTRATION.md.")


def print_check(rows):
    print("\n" + "=" * 78)
    print("3) PERSONALITY CHECK BEFORE DAY 1 (mean answer)")
    print("=" * 78)
    keys = sorted({k for r in rows for k in r if k.startswith("check_")})
    if not keys:
        print("  (no check answers)")
        return
    print(f"  {'':<12}" + "".join(f"{k[6:]:>16}" for k in keys))
    for p in PERSONAS:
        vals = [mean([r.get(k) for r in rows if r["persona"] == p]) for k in keys]
        print(f"  {p:<12}" + "".join(f"{'-' if v is None else f'{v:.2f}':>16}" for v in vals))
    print("  Expected: give_stranger high for cooperative, low for selfish; keep_fish and self_first the opposite.")


def print_neutral(by_day, root):
    path = os.path.join(root, "neutral_by_day.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["condition", "day", "turns", "opp_turns", "opp_gives", "give_rate", "steals", "steal_rate"])
        for (c, d), b in sorted(by_day.items()):
            w.writerow([c, d, b["turns"], b["opp_turns"], b["opp_gives"], ratio(b["opp_gives"], b["opp_turns"]),
                        b["steals"], ratio(b["steals"], b["turns"])])
    print("\n" + "=" * 78)
    print("4) NEUTRAL AGENT, DAY BY DAY (exploratory, H4)  -> also saved to neutral_by_day.csv")
    print("=" * 78)
    days = sorted({d for (_, d) in by_day})
    print(f"  {'day':<5}" + "".join(f"{c + ' give':>17}{c + ' steal':>17}" for c in CONDITIONS))
    for d in days:
        line = f"  {d:<5}"
        for c in CONDITIONS:
            b = by_day.get((c, d))
            line += (f"{pct(ratio(b['opp_gives'], b['opp_turns'])):>17}{pct(ratio(b['steals'], b['turns'])):>17}"
                     if b else f"{'-':>17}{'-':>17}")
        print(line)


def pilot_checks(rows):
    print("\n" + "=" * 78)
    print("5) PILOT CHECKS")
    print("=" * 78)
    runs = defaultdict(list)
    for r in rows:
        runs[(r["condition"], r["seed"])].append(r)
    problems = 0
    for (c, s), rs in sorted(runs.items()):
        hungry = sum(r["hungry_nights"] for r in rs)
        early = [f"{r['name']}({r['persona'][:4]}) day {r['death_day']}"
                 for r in rs if r["died"] and r["death_day"] is not None and r["death_day"] < 7]
        few = [f"{r['name']}({r['persona'][:4]}) {r['opp_turns']}" for r in rs if r["opp_turns"] < MIN_OPPORTUNITIES]
        notes = []
        if c == "scarcity" and hungry == 0:
            notes.append("no hunger at all: scarcity is not biting")
        if c == "abundance" and hungry > 3:
            notes.append(f"{hungry} hungry nights in abundance: more than expected")
        if early:
            notes.append("died before day 7: " + ", ".join(early))
        if len(early) == len(rs):
            notes.append("EVERYONE died before day 7")
        if few:
            notes.append(f"fewer than {MIN_OPPORTUNITIES} chances to give: " + ", ".join(few))
        bad = sum(r["unparseable"] for r in rs)
        if bad:
            notes.append(f"{bad} unreadable model replies")
        problems += bool(notes)
        print(f"  {c:<10} seed {s:<4} hungry nights {hungry:<3} " + ("OK" if not notes else "| " + " | ".join(notes)))
    print("\n  Targets: scarcity has real hunger but not everyone dies before day 7; abundance has little hunger;")
    print(f"  each agent gets at least {MIN_OPPORTUNITIES} chances to give. Adjust the food numbers if not.")
    print(f"  {problems} run(s) with notes.")


def main():
    p = argparse.ArgumentParser(description="Analyse island experiment runs.")
    p.add_argument("root", nargs="?", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs"))
    p.add_argument("--pilot", action="store_true", help="also print pilot checks")
    args = p.parse_args()

    runs = load_runs(args.root)
    if not runs:
        raise SystemExit(f"No finished runs found in {args.root}")
    by_day = defaultdict(lambda: defaultdict(int))
    rows = []
    for path, summary, events in runs:
        rows.extend(agent_rows(path, summary, events, by_day))

    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(os.path.join(args.root, "agents.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    counts = defaultdict(int)
    for _, s, _ in runs:
        counts[s.get("condition")] += 1
    print(f"Runs found: " + ", ".join(f"{c} {n}" for c, n in sorted(counts.items())))
    print_table(rows)
    paired_tests(rows)
    print_check(rows)
    print_neutral(by_day, args.root)
    if args.pilot:
        pilot_checks(rows)
    print(f"\nPer-agent data saved to {os.path.join(args.root, 'agents.csv')}")


if __name__ == "__main__":
    main()
