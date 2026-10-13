"""Exercise metadata for the generator: equipment needed and whether it is a compound lift."""
from muscles import EXERCISES, muscles_for

ALL_EQUIPMENT = ["barbell", "dumbbell", "machine", "cable", "kettlebell", "band", "bodyweight"]

_EQUIPMENT_OVERRIDES = {
    "Back Squat": {"barbell"}, "Front Squat": {"barbell"}, "Deadlift": {"barbell"}, "Sumo Deadlift": {"barbell"},
    "Romanian Deadlift": {"barbell"}, "Barbell Hip Thrust": {"barbell"}, "Hip Thrust": {"barbell"},
    "Close Grip Bench Press": {"barbell"}, "T-Bar Row": {"machine"}, "Lat Pulldown": {"machine"},
    "Assisted Pull Up": {"machine"}, "Assisted Chin Up": {"machine"}, "Assisted Dip": {"machine"},
    "Chest Press Machine": {"machine"}, "Reverse Pec Deck": {"machine"}, "Cable Pull Through": {"cable"},
    "Dumbbell Pullover": {"dumbbell"},
}
_EQUIPMENT_KEYWORDS = [
    (("loop band",), "band"), (("barbell",), "barbell"), (("dumbbell",), "dumbbell"), (("kettlebell",), "kettlebell"),
    (("cable",), "cable"),
    (("machine", "leg press", "leg extension", "hamstrings curl", "leg curl", "hack squat", "calf press", "pec deck",
      "hip abductor", "hip adductor", "assisted"), "machine"),
]
_COMPOUND_WORDS = ("press", "squat", "deadlift", "row", "pulldown", "pull up", "chin up", "dip", "lunge", "thrust", "push up")
_NOT_COMPOUND = ("extension", "tricep", "kickback", "raise", "calf", "upright", "crunch", "fly")


def equipment_for(exercise):
    """The single equipment tag an exercise needs (unknown names are treated as bodyweight)."""
    if exercise in _EQUIPMENT_OVERRIDES:
        return set(_EQUIPMENT_OVERRIDES[exercise])
    name = exercise.lower()
    for keys, tag in _EQUIPMENT_KEYWORDS:
        if any(k in name for k in keys):
            return {tag}
    return {"bodyweight"}


def is_compound(exercise):
    name = exercise.lower()
    return any(w in name for w in _COMPOUND_WORDS) and not any(w in name for w in _NOT_COMPOUND)


def builtin_exercises():
    return list(EXERCISES)


def describe(exercise):
    primary, secondary = muscles_for(exercise)
    return {"exercise": exercise, "primary": primary, "secondary": secondary,
            "equipment": equipment_for(exercise), "compound": is_compound(exercise)}
