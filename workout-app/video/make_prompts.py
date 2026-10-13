"""Write text-to-video prompts (prompts.json / prompts.md) for your most-used exercises.

Usage: python make_prompts.py [--limit 25]
Provider-agnostic: paste into whichever video generator you choose. Always review the clip against the form cues before
using it: video models often get grips, bar paths and joint angles wrong.
"""
import argparse
import json
import os

from cues import CUES

HERE = os.path.dirname(os.path.abspath(__file__))
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
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()
    index = [r for r in json.load(open(os.path.join(HERE, "exercise_index.json"))) if r["kind"] == "strength"]
    rows = [r for r in index if r["exercise"] in CUES][:args.limit]
    out = [{"exercise": r["exercise"], "priority": r["priority"], "prompt": prompt_for(r), "reviewed": False} for r in rows]
    json.dump(out, open(os.path.join(HERE, "prompts.json"), "w"), indent=1)
    with open(os.path.join(HERE, "prompts.md"), "w") as f:
        for o in out:
            f.write(f"## {o['priority']}. {o['exercise']}\n\n{o['prompt']}\n\n")
    missing = [r["exercise"] for r in index[:args.limit] if r["exercise"] not in CUES]
    print(f"wrote {len(out)} prompts; no cues yet for: {', '.join(missing) or 'none'}")


if __name__ == "__main__":
    main()
