"""Workout generator. Pure functions, no I/O.

Picks exercises that fill the sets each target muscle needs, within a time budget, from the equipment you have,
preferring exercises you already know. Weights come from your recent estimated 1RM at ~2 reps in reserve.
"""
import math
from collections import defaultdict

from progression import round_to

# (reps, sets, rest seconds) per exercise kind
GOALS = {
    "strength": {"compound": (5, 4, 150), "isolation": (8, 3, 90)},
    "hypertrophy": {"compound": (8, 3, 90), "isolation": (12, 3, 60)},
    "endurance": {"compound": (15, 3, 45), "isolation": (18, 2, 45)},
}
SET_MINUTES = 0.7        # time under tension per set
SETUP_MINUTES = 1.0      # moving to the machine, adjusting the bar
WARMUP_MINUTES = 5
MAX_EXERCISES = 8


def exercise_minutes(sets, rest):
    return SETUP_MINUTES + sets * (SET_MINUTES + rest / 60)


def weight_for(e1rm_kg, reps, days_since):
    """Working weight for `reps` with ~2 in reserve, eased back after a layoff (same rule as progression)."""
    if not e1rm_kg:
        return 0.0
    ease = 0.8 if days_since > 56 else 0.9 if days_since > 28 else 1.0
    return round_to(e1rm_kg * ease / (1 + (reps + 2) / 30))


def plan_exercise(c, goal):
    kind = "compound" if c["compound"] else "isolation"
    reps, sets, rest = GOALS[goal][kind]
    bodyweight = c["equipment"] == {"bodyweight"}
    if bodyweight:
        weight, reason = 0.0, "Bodyweight: use a variation that makes the last reps hard"
    elif c.get("e1rm"):
        weight = weight_for(c["e1rm"], reps, c["days_since"])
        reason = f"From your estimated 1RM of {c['e1rm']:.0f} kg (last done {c['days_since']} days ago), leaving ~2 reps in reserve"
    else:
        weight, reason = 0.0, f"New for you: start light and find a weight where {reps} reps leaves ~2 in reserve"
    return {"exercise": c["exercise"], "sets": sets, "reps": reps, "weight_kg": weight, "rest_seconds": rest,
            "reason": reason, "muscles": c["primary"], "compound": c["compound"]}


def generate(pool, targets, equipment, minutes, goal, variety, rng, exclude=()):
    """pool: [{exercise, primary, secondary, equipment:set, compound, count, e1rm, days_since}];
    targets: {muscle: relative importance}; equipment: set of tags you have. Returns planned exercises in order."""
    total = sum(targets.values())
    if not total:
        return []
    budget = minutes - WARMUP_MINUTES
    approx_sets = max(6.0, budget / 2.4)
    need = {m: v / total * approx_sets for m, v in targets.items()}
    covered = defaultdict(float)
    chosen, used = [], 0.0
    candidates = [c for c in pool if c["equipment"] <= equipment and c["exercise"] not in exclude and c["primary"]]

    while len(chosen) < MAX_EXERCISES:
        best, best_score = None, 0.5
        for c in candidates:
            if c in chosen:
                continue
            kind = "compound" if c["compound"] else "isolation"
            reps, sets, rest = GOALS[goal][kind]
            if used + exercise_minutes(sets, rest) > budget:
                continue
            gain = over = off = 0.0
            for m, w in [(m, 1.0) for m in c["primary"]] + [(m, 0.5) for m in c["secondary"]]:
                s = sets * w
                if m in need:
                    gain += min(max(need[m] - covered[m], 0), s)
                    over += max(0.0, covered[m] + s - need[m] * 1.4)
                else:
                    off += s
            # primary movers off-target are a big miss; secondary spill-over is normal and cheap
            off_primary = sum(sets for m in c["primary"] if m not in need)
            score = gain - 0.5 * over - 0.3 * off - 1.5 * off_primary
            score += (1 - variety) * 0.6 * math.log1p(c.get("count", 0)) + variety * 1.5 * rng.random()
            if c["compound"] and not any(x["compound"] and set(x["primary"]) & set(c["primary"]) for x in chosen):
                score += 1.5
            if score > best_score:
                best, best_score = c, score
        if not best:
            break
        kind = "compound" if best["compound"] else "isolation"
        _, sets, rest = GOALS[goal][kind]
        chosen.append(best)
        used += exercise_minutes(sets, rest)
        for m in best["primary"]:
            covered[m] += sets
        for m in best["secondary"]:
            covered[m] += sets * 0.5

    chosen.sort(key=lambda c: (not c["compound"], -len(c["primary"])))   # stable: heavy multi-joint lifts first
    plan = [plan_exercise(c, goal) for c in chosen]
    lead = next((p for p in plan if p["compound"] and p["weight_kg"] >= 20), None)
    if lead:
        lead["warmup"] = f"Warm-up: 8 × {round_to(lead['weight_kg'] * 0.5):g} kg, 4 × {round_to(lead['weight_kg'] * 0.7):g} kg"
    return plan


def estimated_minutes(plan):
    return round(WARMUP_MINUTES + sum(exercise_minutes(p["sets"], p["rest_seconds"]) for p in plan))
