"""Per-muscle recovery from logged working sets. Pure functions, no I/O.

Each session leaves a fatigue that decays linearly to zero over a recovery time. The time depends on the muscle
(big muscles take longer) and on how much work was done (more hard sets take longer). Fatigue from several recent
sessions adds up, capped at 100%.
"""
from datetime import datetime

from muscles import MUSCLES, muscles_for

BASE_HOURS = {"chest": 72, "back": 72, "quads": 72, "hamstrings": 72, "glutes": 72,
              "shoulders": 48, "biceps": 48, "triceps": 48, "calves": 48, "core": 36}
PRIMARY, SECONDARY = 1.0, 0.5


def stress_by_muscle(exercise_sets):
    """exercise_sets: iterable of exercise names, one per working set. Returns {muscle: effective hard sets}."""
    stress = {}
    for ex in exercise_sets:
        primary, secondary = muscles_for(ex)
        for m in primary:
            stress[m] = stress.get(m, 0) + PRIMARY
        for m in secondary:
            stress[m] = stress.get(m, 0) + SECONDARY
    return stress


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def status_of(pct):
    return "ready" if pct >= 85 else "recovering" if pct >= 50 else "fatigued"


def recovery(sessions, now: datetime):
    """sessions: [{"end": datetime, "exercises": [name per working set]}]. Returns one row per muscle, most fatigued first."""
    events = {m: [] for m in MUSCLES}
    for s in sessions:
        for m, st in stress_by_muscle(s["exercises"]).items():
            events[m].append((s["end"], st))
    rows = []
    for m in MUSCLES:
        fatigue = 0.0
        for end, st in events[m]:
            needed = BASE_HOURS[m] * clamp(0.5 + st / 8, 0.6, 1.5)
            hours = max(0.0, (now - end).total_seconds() / 3600)
            initial = min(1.0, 0.4 + st / 6)
            fatigue += initial * max(0.0, 1 - hours / needed)
        pct = round(100 * (1 - min(1.0, fatigue)))
        last = max((e for e, _ in events[m]), default=None)
        rows.append({"muscle": m, "recovery_pct": pct, "status": status_of(pct),
                     "last_trained": last.isoformat(timespec="seconds") if last else None})
    return sorted(rows, key=lambda r: r["recovery_pct"])


def template_loads(template_exercises):
    """Planned sets per muscle for a template ({"exercise", "sets"} rows)."""
    load = {}
    for e in template_exercises:
        primary, secondary = muscles_for(e["exercise"])
        for m in primary:
            load[m] = load.get(m, 0) + e["sets"] * PRIMARY
        for m in secondary:
            load[m] = load.get(m, 0) + e["sets"] * SECONDARY
    return load


def template_readiness(template_exercises, recovery_rows):
    """How ready you are for a template: recovery of the muscles it loads, weighted by planned sets."""
    pct = {r["muscle"]: r["recovery_pct"] for r in recovery_rows}
    load = template_loads(template_exercises)
    total = sum(load.values())
    if not total:
        return {"readiness": 100, "limiting_muscle": None}
    readiness = sum(pct[m] * v for m, v in load.items()) / total
    big = [m for m, v in load.items() if v >= 0.25 * max(load.values())]
    return {"readiness": round(readiness), "limiting_muscle": min(big, key=lambda m: pct[m])}
