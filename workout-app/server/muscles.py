"""Which muscles each exercise works. Primary = main movers, secondary = assisting. Unknown names fall back to keywords."""

MUSCLES = ["chest", "back", "shoulders", "biceps", "triceps", "quads", "hamstrings", "glutes", "calves", "core"]

_PRESS = (["chest"], ["triceps", "shoulders"])
_FLY = (["chest"], ["shoulders"])
_TRI = (["triceps"], [])
_ROW = (["back"], ["biceps"])
_CURL = (["biceps"], [])
_OHP = (["shoulders"], ["triceps"])
_DELT = (["shoulders"], [])
_SQUAT = (["quads"], ["glutes", "hamstrings"])
_LUNGE = (["quads", "glutes"], ["hamstrings"])
_CALF = (["calves"], [])
_CORE = (["core"], [])
_HIP = (["glutes"], [])

EXERCISES = {
    "Barbell Bench Press": _PRESS, "Dumbbell Bench Press": _PRESS, "Barbell Incline Bench Press": _PRESS,
    "Dumbbell Incline Bench Press": _PRESS, "Dumbbell Floor Press": _PRESS, "Decline Push Up": _PRESS,
    "Push Up": _PRESS, "Incline Push Up": _PRESS, "Push Up on Knees": _PRESS, "Rotation Push Up": _PRESS,
    "Downward Dog Push Up": (["shoulders"], ["triceps", "chest"]),
    "Cable Crossover Fly": _FLY, "Dumbbell Fly": _FLY, "Machine Fly": _FLY, "Dumbbell Incline Fly": _FLY,
    "Assisted Dip": (["triceps"], ["chest", "shoulders"]), "Bench Dip": (["triceps"], ["chest", "shoulders"]),
    "Tricep Push Up": (["triceps"], ["chest"]),
    "Dumbbell Tricep Extension": _TRI, "Cable Tricep Pushdown": _TRI, "Cable Rope Tricep Extension": _TRI,
    "Dumbbell Kickbacks": _TRI, "Dumbbell Skullcrusher": _TRI, "Mini Loop Band Tricep Press": _TRI,
    "Dumbbell Row": _ROW, "Machine Row": _ROW, "Cable Row": _ROW, "Bent Over Barbell Row": _ROW,
    "Dumbbell Bent Over Row": _ROW, "Inverted Row": _ROW, "Incline Dumbbell Row": _ROW, "Renegade Row": _ROW,
    "Bird Dog Rows": _ROW, "Mini Loop Band Kneeling Row": _ROW,
    "Lat Pulldown": _ROW, "Single Arm Lat Pulldown": _ROW, "Assisted Pull Up": _ROW, "Assisted Chin Up": _ROW,
    "Dumbbell Shrug": (["back"], []), "Barbell Shrug": (["back"], []),
    "Cable Face Pull": (["shoulders"], ["back"]),
    "Deadlift": (["hamstrings", "glutes", "back"], ["quads", "core"]),
    "Sumo Deadlift": (["glutes", "hamstrings", "back"], ["quads", "core"]),
    "Dumbbell Bicep Curl": _CURL, "Barbell Curl": _CURL, "Single Arm Cable Bicep Curl": _CURL,
    "Seated Dumbbell Curl": _CURL, "Hammer Curls": _CURL, "Mini Loop Band Kneeling Bicep Curl": _CURL,
    "Barbell Shoulder Press": _OHP, "Dumbbell Shoulder Press": _OHP, "Arnold Dumbbell Press": _OHP,
    "Seated Barbell Shoulder Press": _OHP,
    "Dumbbell Lateral Raise": _DELT, "Dumbbell Front Raise": _DELT, "Dumbbell Rear Delt Raise": _DELT,
    "Machine Rear Delt Fly": _DELT, "Dumbbell Bent Over Reverse Fly": _DELT, "Dumbbell Upright Row": (["shoulders"], ["back"]),
    "Cable Upright Row": (["shoulders"], ["back"]),
    "Back Squat": _SQUAT, "Front Squat": _SQUAT, "Kettlebell Goblet Squat": _SQUAT, "Dumbbell Squat": _SQUAT,
    "Leg Press": _SQUAT, "Machine Leg Press": _SQUAT, "Air Squats": _SQUAT, "Leg Extension": (["quads"], []),
    "Lying Hamstrings Curl": (["hamstrings"], []), "Seated Leg Curl": (["hamstrings"], []),
    "Dumbbell Lunge": _LUNGE, "Lunge": _LUNGE, "Walking Lunge": _LUNGE, "Side Lunge": _LUNGE,
    "Standing Barbell Calf Raise": _CALF, "Calf Raise": _CALF, "Standing Machine Calf Press": _CALF,
    "Hip Thrust": _HIP, "Dumbbell Hip Thrust": _HIP, "Cable Hip Abduction": _HIP, "Cable Hip Adduction": _HIP,
    "Machine Hip Abductor": _HIP, "Machine Hip Adductor": _HIP, "Kettlebell Swing": (["glutes", "hamstrings"], ["back"]),
    "Cable Pull Through": (["glutes", "hamstrings"], []),
    "Russian Twist": _CORE, "Bicycle Crunch": _CORE, "Exercise Ball Crunch": _CORE, "Hanging Leg Raise": _CORE,
    "Hanging Knee Raise": _CORE, "Flutter Kicks": _CORE, "Plank": _CORE, "Dumbbell Side Bend": _CORE,
}

# Common exercises you haven't logged yet; they give the generator and swaps something to offer beyond your history.
EXERCISES.update({
    "Pull Up": _ROW, "Chin Up": _ROW, "Romanian Deadlift": (["hamstrings", "glutes"], ["back"]),
    "Dumbbell Romanian Deadlift": (["hamstrings", "glutes"], ["back"]), "Bulgarian Split Squat": _LUNGE,
    "Hack Squat": _SQUAT, "Barbell Hip Thrust": _HIP, "Glute Bridge": _HIP, "Seated Calf Raise": _CALF,
    "Chest Press Machine": _PRESS, "Close Grip Bench Press": (["triceps"], ["chest", "shoulders"]),
    "Overhead Triceps Extension": _TRI, "Cable Lateral Raise": _DELT, "Cable Rear Delt Fly": _DELT,
    "Reverse Pec Deck": _DELT, "Preacher Curl": _CURL, "Cable Curl": _CURL, "Incline Dumbbell Curl": _CURL,
    "T-Bar Row": _ROW, "Dumbbell Pullover": (["back"], ["chest"]), "Dumbbell Goblet Squat": _SQUAT,
    "Cable Crunch": _CORE, "Pallof Press": _CORE, "Dead Bug": _CORE,
})

# Checked in order for names not listed above; first match wins.
KEYWORDS = [
    (("shoulder raise", "shoulder squeeze"), _DELT), (("clam", "lateral walk"), _HIP), (("superman",), (["back"], [])),
    (("pull-in", "mountain climber", "toe touch"), _CORE),
    (("calf",), _CALF), (("hamstring", "leg curl", "romanian"), (["hamstrings"], ["glutes"])),
    (("squat", "leg press", "lunge", "leg extension"), _SQUAT), (("hip", "glute", "bridge", "kickback"), _HIP),
    (("deadlift",), (["hamstrings", "glutes", "back"], ["quads"])),
    (("tricep", "skullcrusher", "dip"), _TRI), (("curl",), _CURL),
    (("lateral raise", "front raise", "rear delt", "upright row", "shoulder press", "overhead"), _OHP),
    (("fly", "bench", "push up", "chest"), _PRESS), (("row", "pulldown", "pull up", "chin up", "shrug"), _ROW),
    (("crunch", "twist", "plank", "sit up", "leg raise", "knee raise", "kick"), _CORE),
]


def muscles_for(exercise):
    """Returns (primary, secondary) muscle lists; both empty when the exercise is unknown."""
    if exercise in EXERCISES:
        return EXERCISES[exercise]
    name = exercise.lower()
    for keys, m in KEYWORDS:
        if any(k in name for k in keys):
            return m
    return ([], [])
