"""Write text-to-video prompts (prompts.json / prompts.md) for the exercises that have form cues (your most-used ones).

Usage: python make_prompts.py [--limit 25]
Provider-agnostic: paste into whichever video generator you choose. Always review the clip against the form cues before
using it: video models often get grips, bar paths and joint angles wrong.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server"))
from cues import CUES  # noqa: E402
from media import slug  # noqa: E402

EQUIPMENT = {"barbell": "a barbell with weight plates", "dumbbell": "a pair of dumbbells", "machine": "a gym machine",
             "cable": "a cable machine", "kettlebell": "a kettlebell", "band": "a resistance band",
             "bodyweight": "no equipment"}
STYLE = ("Realistic instructional fitness video. One athletic adult in plain dark training clothes in a clean, bright gym. "
         "Fixed camera at a three-quarter front angle, full body in frame, no camera movement, no cuts. "
         "Slow, controlled, smooth repetitions: exactly 3 reps. No text, logos or music.")


def prompt_for(row):
    cue = CUES[row["exercise"]]
    return (f"{STYLE} The exercise is the {row['exercise']} using {EQUIPMENT[row['equipment']]}. "
            f"Correct technique: {cue}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()
    index = [r for r in json.load(open(os.path.join(HERE, "exercise_index.json"))) if r["kind"] == "strength"]
    rows = [r for r in index if r["exercise"] in CUES][:args.limit]
    out = [{"exercise": r["exercise"], "priority": r["priority"], "prompt": prompt_for(r), "save_as": f"clips/{slug(r['exercise'])}.mp4", "reviewed": False} for r in rows]
    json.dump(out, open(os.path.join(HERE, "prompts.json"), "w"), indent=1)
    with open(os.path.join(HERE, "prompts.md"), "w") as f:
        for o in out:
            f.write(f"## {o['priority']}. {o['exercise']}\n\nSave the clip as `{o['save_as']}`\n\n{o['prompt']}\n\n")
    missing = [r["exercise"] for r in index[:args.limit] if r["exercise"] not in CUES]
    print(f"wrote {len(out)} prompts; no cues yet for: {', '.join(missing) or 'none'}")


if __name__ == "__main__":
    main()
