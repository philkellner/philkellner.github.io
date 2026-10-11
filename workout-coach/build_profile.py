"""Turn a workout CSV export into profile.json (templates + lift stats) for the coach bot.

Usage: python build_profile.py WorkoutExport.csv
"""
import json, sys
import pandas as pd

GROUPS = {
    "chest": ["Barbell Bench Press", "Dumbbell Bench Press", "Barbell Incline Bench Press", "Cable Crossover Fly",
              "Decline Push Up", "Dumbbell Fly", "Dumbbell Incline Bench Press", "Dumbbell Floor Press", "Machine Fly",
              "Dumbbell Incline Fly", "Push Up", "Incline Push Up", "Push Up on Knees", "Rotation Push Up",
              "Downward Dog Push Up", "Dumbbell Tricep Extension", "Cable Tricep Pushdown", "Assisted Dip",
              "Cable Rope Tricep Extension", "Dumbbell Kickbacks", "Mini Loop Band Tricep Press", "Tricep Push Up",
              "Bench Dip", "Dumbbell Skullcrusher"],
    "back": ["Dumbbell Row", "Lat Pulldown", "Machine Row", "Assisted Pull Up", "Bent Over Barbell Row", "Cable Row",
             "Inverted Row", "Dumbbell Bent Over Row", "Assisted Chin Up", "Renegade Row", "Incline Dumbbell Row",
             "Single Arm Lat Pulldown", "Mini Loop Band Kneeling Row", "Bird Dog Rows", "Dumbbell Bicep Curl",
             "Barbell Curl", "Single Arm Cable Bicep Curl", "Seated Dumbbell Curl", "Hammer Curls",
             "Mini Loop Band Kneeling Bicep Curl"],
    "shoulders": ["Barbell Shoulder Press", "Dumbbell Upright Row", "Dumbbell Lateral Raise", "Arnold Dumbbell Press",
                  "Dumbbell Front Raise", "Machine Rear Delt Fly", "Dumbbell Rear Delt Raise",
                  "Dumbbell Shoulder Press", "Cable Face Pull", "Dumbbell Bent Over Reverse Fly",
                  "Cable Upright Row", "Seated Barbell Shoulder Press", "Dumbbell Shrug", "Barbell Shrug"],
    "legs": ["Back Squat", "Deadlift", "Standing Barbell Calf Raise", "Leg Press", "Kettlebell Goblet Squat",
             "Lying Hamstrings Curl", "Leg Extension", "Dumbbell Lunge", "Calf Raise", "Dumbbell Squat",
             "Machine Leg Press", "Seated Leg Curl", "Front Squat", "Sumo Deadlift", "Standing Machine Calf Press",
             "Hip Thrust", "Dumbbell Hip Thrust", "Lunge", "Walking Lunge"],
}
NAMES = {"chest": "Chest & Triceps", "back": "Back & Biceps", "shoulders": "Shoulders", "legs": "Legs"}
EXERCISE_GROUP = {e: g for g, es in GROUPS.items() for e in es}
KG_TO_LB = 2.20462


def load(path):
    d = pd.read_csv(path, skipinitialspace=True)
    d["Date"] = pd.to_datetime(d["Date"].str[:19])
    d["day"] = d.Date.dt.date
    d["grp"] = d.Exercise.map(EXERCISE_GROUP)
    return d


def label_sessions(w):
    counts = w.groupby(["day", "grp"]).size().unstack(fill_value=0)
    share = counts.div(counts.sum(axis=1), axis=0)
    # a session belongs to the muscle group holding >= 35% of its working sets, if exactly one does
    lab = share.apply(lambda r: "+".join(sorted(r.index[r >= 0.35])), axis=1)
    return lab.to_dict()


def epley(kg, reps):
    return kg * (1 + reps / 30)


def main(path):
    d = load(path)
    w = d[(~d.isWarmup) & d.grp.notna()].copy()
    w["type"] = w.day.map(label_sessions(w))
    w = w[w.type.isin(NAMES)].sort_values("Date")

    templates = {}
    for t, name in NAMES.items():
        s = w[w.type == t].copy()
        n = s.day.nunique()
        s["ord"] = s.groupby("day").Exercise.transform(lambda x: pd.factorize(x)[0])
        g = s.groupby("Exercise").agg(days=("day", "nunique"), ord=("ord", "mean"))
        g = g[g.days >= n * 0.25].sort_values("days", ascending=False).head(7).sort_values("ord")
        rows = []
        for ex, r in g.iterrows():
            x = s[s.Exercise == ex]
            recent = x[x.day.isin(sorted(x.day.unique())[-5:])]
            top = recent.groupby("day")["Weight(kg)"].max().median()
            rows.append({"exercise": ex, "sets": int(round(x.groupby("day").size().median())),
                         "reps": int(round(recent.Reps.median())), "weight_kg": round(float(top), 1),
                         "weight_lb": int(round(top * KG_TO_LB / 5) * 5), "sessions_logged": int(r.days)})
        templates[name] = {"sessions_in_history": int(n), "exercises": rows}

    lifts = {}
    for ex, x in w.groupby("Exercise"):
        if x.day.nunique() < 5:
            continue
        x = x[x.Reps.between(1, 12) & (x["Weight(kg)"] > 0)]
        if x.empty:
            continue
        best = x.loc[x.apply(lambda r: epley(r["Weight(kg)"], r.Reps), axis=1).idxmax()]
        last_day = x.day.max()
        last = x[x.day == last_day]
        lifts[ex] = {"best_set": f'{best["Weight(kg)"]:.1f}kg x {int(best.Reps)} on {best.day}',
                     "est_1rm_kg": round(epley(best["Weight(kg)"], best.Reps), 1),
                     "last_session": str(last_day),
                     "last_sets": [f'{r["Weight(kg)"]:.1f}kg x {int(r.Reps)}' for _, r in last.iterrows()]}

    lifting_days = sorted(w.day.unique())
    profile = {
        "history": {"first_lifting_day": str(lifting_days[0]), "last_lifting_day": str(lifting_days[-1]),
                    "lifting_sessions": len(lifting_days)},
        "templates": templates,
        "lifts": lifts,
    }
    with open("profile.json", "w") as f:
        json.dump(profile, f, indent=1)
    print(json.dumps(templates, indent=1))
    print(f"wrote profile.json ({len(lifts)} lifts)")


if __name__ == "__main__":
    main(sys.argv[1])
