"""Import a workout CSV export (Date, Exercise, Reps, Weight(kg), isWarmup, ...) as finished sessions.

Usage: python import_history.py WorkoutExport.csv
Safe to re-run: sessions whose start time already exists are skipped. Cardio rows (no reps) are ignored.
"""
import csv
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

import app

# Checked in order, first match wins (so "Upright Row" is shoulders, "Leg Curl" is legs).
RULES = [("Legs", ("squat", "deadlift", "leg ", "calf", "lunge", "hip", "hamstring", "kettlebell")),
         ("Shoulders", ("shoulder press", "arnold", "lateral raise", "front raise", "rear delt", "upright", "shrug", "face pull", "reverse fly")),
         ("Chest & Triceps", ("bench", "fly", "push up", "tricep", "dip", "skullcrusher", "kickback")),
         ("Back & Biceps", ("row", "pulldown", "pull up", "chin up", "curl"))]


def group_of(exercise):
    e = exercise.lower() + " "
    for name, keys in RULES:
        if any(k in e for k in keys):
            return name
    return None


def parse_date(s):
    return datetime.strptime(s.strip()[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def load(path):
    days = defaultdict(list)
    with open(path, newline="") as f:
        for r in csv.DictReader(f, skipinitialspace=True):
            reps = int(float(r["Reps"] or 0))
            if reps <= 0:
                continue
            when = parse_date(r["Date"])
            days[when.date()].append({"when": when, "exercise": r["Exercise"].strip(), "reps": reps,
                                      "kg": float(r["Weight(kg)"] or 0), "warmup": r["isWarmup"].strip().lower() == "true"})
    return days


def session_name(sets):
    counts = defaultdict(int)
    for s in sets:
        g = group_of(s["exercise"])
        if g and not s["warmup"]:
            counts[g] += 1
    return max(counts, key=counts.get) if counts else "Workout"


def import_days(days):
    added = skipped = 0
    with app.db() as con:
        for day in sorted(days):
            sets = sorted(days[day], key=lambda s: s["when"])
            started = sets[0]["when"].isoformat(timespec="seconds")
            if con.execute("SELECT 1 FROM sessions WHERE started_at=?", (started,)).fetchone():
                skipped += 1
                continue
            sid = con.execute("INSERT INTO sessions (template_id,name,started_at,finished_at,source) VALUES (NULL,?,?,?,'import')",
                              (session_name(sets), started, sets[-1]["when"].isoformat(timespec="seconds"))).lastrowid
            order, idx = [], defaultdict(int)
            for s in sets:
                if s["exercise"] not in order:
                    order.append(s["exercise"])
                idx[s["exercise"]] += 1
                con.execute("INSERT INTO session_sets (session_id,exercise,set_index,reps,weight_kg,completed_at,is_warmup) "
                            "VALUES (?,?,?,?,?,?,?)", (sid, s["exercise"], idx[s["exercise"]], s["reps"], s["kg"],
                                                      s["when"].isoformat(timespec="seconds"), int(s["warmup"])))
            for pos, ex in enumerate(order):
                work = [s for s in sets if s["exercise"] == ex and not s["warmup"]] or [s for s in sets if s["exercise"] == ex]
                con.execute("INSERT INTO session_exercises (session_id,position,exercise,sets,reps,weight_kg) VALUES (?,?,?,?,?,?)",
                            (sid, pos, ex, len(work), int(statistics.median(w["reps"] for w in work)), max(w["kg"] for w in work)))
            added += 1
        app.derive_profiles(con)   # equipment profiles that match what you actually train with
    return added, skipped


if __name__ == "__main__":
    added, skipped = import_days(load(sys.argv[1]))
    print(f"imported {added} sessions, skipped {skipped} already present")
