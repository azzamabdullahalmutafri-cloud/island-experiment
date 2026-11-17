#!/usr/bin/env python3
"""
Run the whole experiment: every seed in both conditions.

  python run_all.py                    # seeds 1-20, abundance + scarcity  -> runs/
  python run_all.py --pilot            # seeds 101-103 (not used in the analysis) -> runs_pilot/
  python run_all.py --seeds 1-5        # only some seeds
  python run_all.py --mock --days 3    # quick test without Ollama

It can be stopped at any time (Ctrl+C) and started again: finished runs are skipped,
and a half-finished run is moved aside and started over.
For each seed both conditions run back to back, so finished results always come in pairs.
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime


def parse_seeds(text):
    seeds = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            seeds.extend(range(int(a), int(b) + 1))
        elif part:
            seeds.append(int(part))
    return seeds


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(description="Run all seeds in both conditions.")
    p.add_argument("--seeds", help="e.g. 1-20 or 1,2,7 (default 1-20, or 101-103 with --pilot)")
    p.add_argument("--conditions", default="abundance,scarcity")
    p.add_argument("--pilot", action="store_true", help="pilot runs, saved in runs_pilot/")
    p.add_argument("--out", help="output folder (default runs/ or runs_pilot/)")
    p.add_argument("--config", default=os.path.join(here, "config.json"))
    p.add_argument("--mock", action="store_true")
    p.add_argument("--days", type=int)
    p.add_argument("--model")
    args = p.parse_args()

    seeds = parse_seeds(args.seeds or ("101-103" if args.pilot else "1-20"))
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    root = args.out or os.path.join(here, "runs_pilot" if args.pilot else "runs")
    os.makedirs(root, exist_ok=True)

    jobs = [(s, c) for s in seeds for c in conditions]
    done = failed = 0
    start = time.time()
    print(f"{len(jobs)} runs: seeds {seeds[0]}..{seeds[-1]} x {', '.join(conditions)} -> {root}")
    for i, (seed, cond) in enumerate(jobs, 1):
        out = os.path.join(root, cond, f"seed_{seed:03d}")
        if os.path.exists(os.path.join(out, "summary.json")):
            print(f"[{i}/{len(jobs)}] {cond} seed {seed}: already done, skipping")
            done += 1
            continue
        if os.path.isdir(out):
            aside = out + "_incomplete_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            os.rename(out, aside)
            print(f"[{i}/{len(jobs)}] {cond} seed {seed}: moved half-finished run to {aside}")
        cmd = [sys.executable, os.path.join(here, "island.py"), "--config", args.config,
               "--condition", cond, "--seed", str(seed), "--out", out]
        if args.mock:
            cmd.append("--mock")
        if args.days:
            cmd += ["--days", str(args.days)]
        if args.model:
            cmd += ["--model", args.model]
        print(f"\n[{i}/{len(jobs)}] {cond} seed {seed} ...")
        t0 = time.time()
        code = subprocess.run(cmd).returncode
        mins = (time.time() - t0) / 60
        if code == 0 and os.path.exists(os.path.join(out, "summary.json")):
            done += 1
            remaining = len(jobs) - i
            avg = (time.time() - start) / 60 / i
            print(f"[{i}/{len(jobs)}] finished in {mins:.1f} min. About {remaining * avg / 60:.1f} h left.")
        else:
            failed += 1
            print(f"[{i}/{len(jobs)}] FAILED (exit code {code}). Run this script again to retry.")

    print(f"\nDone: {done} finished, {failed} failed, out of {len(jobs)}.")
    print(f"Next: python analyze.py {root}" + (" --pilot" if args.pilot else ""))


if __name__ == "__main__":
    main()
