"""Index every exercise in a workout CSV export, ranked by how much you do it.

Usage: python build_index.py WorkoutExport.csv
Writes exercise_index.json / .csv / .md next to this script.
"""
import csv
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server"))
from library import describe  # noqa: E402


def load(path):
    ex = defaultdict(lambda: {"days": set(), "sets": 0, "strength_rows": 0, "rows": 0})
    with open(path, newline="") as f:
        for r in csv.DictReader(f, skipinitialspace=True):
            e = ex[r["Exercise"].strip()]
            e["rows"] += 1
            e["days"].add(r["Date"][:10])
            if int(float(r["Reps"] or 0)) > 0:
                e["strength_rows"] += 1
                if r["isWarmup"].strip().lower() != "true":
                    e["sets"] += 1
    return ex


def build(path):
    rows = []
    for name, e in load(path).items():
        d = describe(name)
        days = sorted(e["days"])
        rows.append({
            "exercise": name,
            "kind": "strength" if e["strength_rows"] else "cardio",
            "sessions": len(days), "working_sets": e["sets"], "first_done": days[0], "last_done": days[-1],
            "primary": d["primary"], "secondary": d["secondary"], "equipment": sorted(d["equipment"])[0],
            "compound": d["compound"],
            "youtube_query": f"{name} exercise proper form",
        })
    rows.sort(key=lambda r: (-r["sessions"], r["exercise"]))
    for i, r in enumerate(rows, 1):
        r["priority"] = i
    return rows


def coverage(rows, k):
    total = sum(r["sessions"] for r in rows)
    return sum(r["sessions"] for r in rows[:k]) / total if total else 0


def write(rows):
    with open(os.path.join(HERE, "exercise_index.json"), "w") as f:
        json.dump(rows, f, indent=1)
    with open(os.path.join(HERE, "exercise_index.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["priority", "exercise", "kind", "sessions", "working_sets", "last_done", "primary", "equipment", "compound"])
        for r in rows:
            w.writerow([r["priority"], r["exercise"], r["kind"], r["sessions"], r["working_sets"], r["last_done"],
                        "/".join(r["primary"]), r["equipment"], r["compound"]])
    with open(os.path.join(HERE, "exercise_index.md"), "w") as f:
        f.write("| # | Exercise | Kind | Sessions | Muscles | Equipment |\n|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['priority']} | {r['exercise']} | {r['kind']} | {r['sessions']} | {', '.join(r['primary']) or '-'} | {r['equipment']} |\n")


if __name__ == "__main__":
    rows = build(sys.argv[1])
    write(rows)
    strength = [r for r in rows if r["kind"] == "strength"]
    print(f"{len(rows)} exercises ({len(strength)} strength, {len(rows) - len(strength)} cardio)")
    for k in (10, 25, 40):
        print(f"top {k} exercises cover {coverage(rows, k):.0%} of all exercise-sessions")
