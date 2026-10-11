"""Load template days from the coach bot's profile.json: python seed.py ../../workout-coach/profile.json"""
import json
import sys

import app

profile = json.load(open(sys.argv[1]))
with app.db() as con:
    existing = {r["name"] for r in con.execute("SELECT name FROM templates")}
for name, t in profile["templates"].items():
    if name in existing:
        print("skip (exists):", name)
        continue
    app.create_template(app.TemplateIn(name=name, exercises=[
        app.ExerciseIn(exercise=e["exercise"], sets=e["sets"], reps=e["reps"], weight_kg=e["weight_kg"])
        for e in t["exercises"]]))
    print("added:", name)
