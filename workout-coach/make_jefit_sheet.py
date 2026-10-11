import json
p = json.load(open("profile.json"))
out = ["# JEFIT template days\n",
       "JEFIT has no import for routines, so create one routine per day (Workout > Routines > Create) and add these exercises.\n"]
for name, t in p["templates"].items():
    out.append(f"\n## {name} day\n\n| # | Exercise | Sets x Reps | Start weight |\n|---|---|---|---|")
    for i, e in enumerate(t["exercises"], 1):
        out.append(f'| {i} | {e["exercise"]} | {e["sets"]} x {e["reps"]} | {e["weight_lb"]} lb / {e["weight_kg"]} kg |')
open("jefit_templates.md", "w").write("\n".join(out) + "\n")
