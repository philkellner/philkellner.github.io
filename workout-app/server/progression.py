"""Double-progression weight suggestions.

If you hit the target reps on every planned set, add weight. Miss them, repeat the weight. Miss them twice in a row at
the same weight, deload ~10%. After a layoff, restart lighter. Pure functions, no I/O.
"""
from datetime import datetime

LOWER_COMPOUNDS = {"Back Squat", "Front Squat", "Deadlift", "Sumo Deadlift", "Leg Press", "Machine Leg Press"}
SAME_WEIGHT_TOL = 0.3  # kg; imported data has unit-conversion noise


def round_to(x):
    """Nearest loadable weight: 2.5 kg steps, or 1.25 kg for light dumbbell-sized loads."""
    step = 2.5 if x >= 10 else 1.25
    return round(round(x / step) * step, 2)


def increment(exercise, weight_kg):
    if exercise in LOWER_COMPOUNDS:
        return 5.0
    return 2.5 if weight_kg >= 10 else 1.25


def working(sets):
    """Sets near the session's top weight; this drops ramp-up sets that weren't flagged as warm-ups."""
    top = max(s["weight_kg"] for s in sets)
    return [s for s in sets if s["weight_kg"] >= top * 0.9 - SAME_WEIGHT_TOL]


def hit_target(sets, goal_sets, goal_reps):
    return len(sets) >= goal_sets and all(s["reps"] >= goal_reps for s in sets)


def suggest(exercise, sessions, goal_sets, goal_reps, now: datetime):
    """sessions: newest first, each {"date": datetime, "sets": [{"reps", "weight_kg"}]} with warm-ups excluded.
    Returns {"weight_kg", "reps", "reason"} or None when there is no history."""
    sessions = [s for s in sessions if s["sets"]]
    if not sessions:
        return None
    last = sessions[0]
    work = working(last["sets"])
    w = max(s["weight_kg"] for s in work)
    days = (now - last["date"]).days
    hit = hit_target(work, goal_sets, goal_reps)
    unit = f"{w:.1f} kg"

    if w == 0:  # bodyweight: progress by reps
        reps = goal_reps + 1 if hit else goal_reps
        return {"weight_kg": 0, "reps": reps, "reason": f"Bodyweight: aim for {reps} reps"}

    if days > 56:
        return {"weight_kg": round_to(w * 0.8), "reps": goal_reps,
                "reason": f"{days} days since last time: restart at 80% of {unit}"}
    if days > 28:
        return {"weight_kg": round_to(w * 0.9), "reps": goal_reps,
                "reason": f"{days} days since last time: restart at 90% of {unit}"}

    if hit:
        inc = increment(exercise, w)
        return {"weight_kg": round_to(w + inc), "reps": goal_reps,
                "reason": f"Hit {goal_reps} reps on all {len(work)} sets at {unit}: add {inc:g} kg"}

    if len(sessions) > 1:
        prev = sessions[1]
        prev_work = working(prev["sets"])
        prev_w = max(s["weight_kg"] for s in prev_work)
        if abs(prev_w - w) <= SAME_WEIGHT_TOL and not hit_target(prev_work, goal_sets, goal_reps) \
                and (last["date"] - prev["date"]).days <= 21:
            return {"weight_kg": round_to(w * 0.9), "reps": goal_reps,
                    "reason": f"Missed {goal_reps} reps twice at {unit}: deload ~10%"}
    return {"weight_kg": round_to(w), "reps": goal_reps,
            "reason": f"Missed {goal_reps} reps on some sets at {unit}: repeat the weight"}
