import os
import tempfile
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "c.db"))
os.environ.setdefault("API_TOKEN", "secret")

from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402
import progression as pg  # noqa: E402
import recovery as rc  # noqa: E402
from muscles import muscles_for  # noqa: E402

NOW = datetime(2030, 1, 10, 12, tzinfo=timezone.utc)
H = {"Authorization": "Bearer secret"}
c = TestClient(app.app)


def sess(days_ago, *sets):
    return {"date": NOW - timedelta(days=days_ago), "sets": [{"reps": r, "weight_kg": w} for r, w in sets]}


# ---- progression ----
def test_hit_target_adds_weight():
    s = pg.suggest("Barbell Bench Press", [sess(3, (7, 60), (7, 60), (8, 60))], 3, 7, NOW)
    assert (s["weight_kg"], s["reps"]) == (62.5, 7) and "add 2.5" in s["reason"]


def test_lower_body_compound_jumps_more():
    s = pg.suggest("Back Squat", [sess(3, (5, 100), (5, 100), (5, 100))], 3, 5, NOW)
    assert s["weight_kg"] == 105


def test_missed_reps_repeats_weight():
    s = pg.suggest("Barbell Bench Press", [sess(3, (7, 60), (6, 60), (5, 60))], 3, 7, NOW)
    assert s["weight_kg"] == 60 and "repeat" in s["reason"]


def test_fewer_sets_than_planned_does_not_count_as_hit():
    assert pg.suggest("Barbell Bench Press", [sess(3, (7, 60), (7, 60))], 3, 7, NOW)["weight_kg"] == 60


def test_missing_twice_at_same_weight_deloads():
    s = pg.suggest("Barbell Bench Press", [sess(3, (6, 60), (5, 60), (5, 60)), sess(10, (6, 60), (6, 60), (5, 60))], 3, 7, NOW)
    assert s["weight_kg"] == 55 and "deload" in s["reason"]


def test_second_miss_at_a_different_weight_just_repeats():
    s = pg.suggest("Barbell Bench Press", [sess(3, (6, 60), (5, 60), (5, 60)), sess(10, (7, 57.5), (7, 57.5), (7, 57.5))], 3, 7, NOW)
    assert s["weight_kg"] == 60


def test_layoff_restarts_lighter():
    assert pg.suggest("Barbell Bench Press", [sess(40, (7, 60), (7, 60), (7, 60))], 3, 7, NOW)["weight_kg"] == 55
    assert pg.suggest("Barbell Bench Press", [sess(70, (7, 60), (7, 60), (7, 60))], 3, 7, NOW)["weight_kg"] == 47.5


def test_unflagged_ramp_up_sets_are_ignored():
    s = pg.suggest("Barbell Bench Press", [sess(3, (8, 20), (5, 100), (5, 100), (5, 100))], 3, 5, NOW)
    assert s["weight_kg"] == 102.5


def test_bodyweight_progresses_reps_and_no_history_is_none():
    assert pg.suggest("Push Up", [sess(3, (10, 0), (10, 0), (10, 0))], 3, 10, NOW)["reps"] == 11
    assert pg.suggest("Push Up", [], 3, 10, NOW) is None


# ---- muscles ----
def test_muscle_mapping_and_fallback():
    assert muscles_for("Barbell Bench Press")[0] == ["chest"]
    assert muscles_for("Some New Cable Tricep Thing")[0] == ["triceps"]
    assert muscles_for("Burpee") == ([], [])


# ---- recovery ----
CHEST_DAY = {"end": NOW, "exercises": ["Barbell Bench Press"] * 4 + ["Dumbbell Tricep Extension"] * 3}


def pct(rows):
    return {r["muscle"]: r["recovery_pct"] for r in rows}


def test_recovery_over_time():
    soon = pct(rc.recovery([CHEST_DAY], NOW + timedelta(hours=1)))
    assert soon["chest"] < 10
    assert soon["quads"] == 100
    mid = pct(rc.recovery([CHEST_DAY], NOW + timedelta(hours=36)))
    assert 30 < mid["chest"] < 70
    assert pct(rc.recovery([CHEST_DAY], NOW + timedelta(days=5)))["chest"] == 100


def test_secondary_muscles_get_less_fatigue_than_primary():
    p = pct(rc.recovery([{"end": NOW, "exercises": ["Barbell Bench Press"] * 4}], NOW + timedelta(hours=12)))
    assert p["chest"] < p["triceps"] < 100


def test_back_to_back_sessions_stack():
    one = pct(rc.recovery([CHEST_DAY], NOW + timedelta(hours=50)))["chest"]
    two = pct(rc.recovery([CHEST_DAY, dict(CHEST_DAY, end=NOW - timedelta(hours=12))], NOW + timedelta(hours=50)))["chest"]
    assert two < one


def test_most_fatigued_first_and_status_labels():
    rows = rc.recovery([CHEST_DAY], NOW + timedelta(hours=1))
    assert rows[0]["muscle"] == "chest" and rows[0]["status"] == "fatigued" and rows[-1]["status"] == "ready"


# ---- API ----
def add_session(name, when, sets):
    """sets: [(exercise, reps, kg)] inserted as a finished session; also records the plan (3 sets of the first reps)."""
    with app.db() as con:
        sid = con.execute("INSERT INTO sessions (name,started_at,finished_at,source) VALUES (?,?,?,'test')",
                          (name, when.isoformat(timespec="seconds"), when.isoformat(timespec="seconds"))).lastrowid
        seen = {}
        for ex, reps, kg in sets:
            seen[ex] = seen.get(ex, 0) + 1
            con.execute("INSERT INTO session_sets (session_id,exercise,set_index,reps,weight_kg,completed_at) VALUES (?,?,?,?,?,?)",
                        (sid, ex, seen[ex], reps, kg, when.isoformat(timespec="seconds")))
        for i, (ex, n) in enumerate(seen.items()):
            reps = next(r for e, r, _ in sets if e == ex)
            con.execute("INSERT INTO session_exercises (session_id,position,exercise,sets,reps,weight_kg) VALUES (?,?,?,?,?,0)",
                        (sid, i, ex, n, reps))
    return sid


def test_recovery_and_recommendation_endpoints():
    c.post("/templates", headers=H, json={"name": "Chest day", "exercises": [
        {"exercise": "Barbell Bench Press", "sets": 4, "reps": 7}, {"exercise": "Dumbbell Tricep Extension", "sets": 3, "reps": 8}]})
    c.post("/templates", headers=H, json={"name": "Leg day", "exercises": [
        {"exercise": "Back Squat", "sets": 4, "reps": 5}, {"exercise": "Lying Hamstrings Curl", "sets": 3, "reps": 10}]})
    trained = datetime(2040, 1, 1, 10, tzinfo=timezone.utc)
    add_session("Chest day", trained, [("Barbell Bench Press", 7, 60)] * 4 + [("Dumbbell Tricep Extension", 8, 15)] * 3)
    as_of = (trained + timedelta(hours=20)).isoformat()
    rec = c.get("/recovery", params={"as_of": as_of}, headers=H).json()
    assert rec[0]["muscle"] == "chest" and rec[0]["recovery_pct"] < 50
    r = c.get("/recommendation", params={"as_of": as_of}, headers=H).json()
    ours = {x["name"]: x for x in r}   # the DB is shared with other tests, so look only at our two templates
    assert ours["Leg day"]["readiness"] > 90 > 50 > ours["Chest day"]["readiness"]
    assert ours["Chest day"]["limiting_muscle"] == "chest"
    assert [x["recommended"] for x in r].count(True) == 1 and r[0]["recommended"]
    assert r[0]["readiness"] >= ours["Leg day"]["readiness"]
    assert c.get("/recovery", params={"as_of": "nonsense"}, headers=H).status_code == 422


def test_starting_a_session_applies_progression():
    recent = datetime.now(timezone.utc) - timedelta(days=3)
    add_session("OHP", recent, [("Barbell Shoulder Press", 6, 40)] * 3)
    tid = c.post("/templates", headers=H, json={"name": "Shoulders", "exercises": [
        {"exercise": "Barbell Shoulder Press", "sets": 3, "reps": 6, "weight_kg": 30},
        {"exercise": "Brand New Exercise", "sets": 3, "reps": 10, "weight_kg": 5}]}).json()["id"]
    s = c.post("/sessions", json={"template_id": tid}, headers=H).json()
    ohp, new = s["exercises"]
    assert ohp["weight_kg"] == 42.5 and ohp["suggestion"]["weight_kg"] == 42.5 and "add 2.5" in ohp["suggestion"]["reason"]
    assert new["weight_kg"] == 5 and new["suggestion"] is None  # no history: keep the template
    assert c.get("/exercises/Barbell Shoulder Press/suggestion", headers=H).json()["reps"] == 6
    assert c.get("/exercises/Brand New Exercise/suggestion", headers=H).status_code == 404
