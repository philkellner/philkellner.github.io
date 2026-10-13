import os
import random
import tempfile
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "g.db"))
os.environ.setdefault("API_TOKEN", "secret")

from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402
import generator as gen  # noqa: E402
import library  # noqa: E402

H = {"Authorization": "Bearer secret"}
c = TestClient(app.app)


def ex(name, count=5, e1rm=100.0, days=3):
    d = library.describe(name)
    return dict(d, count=count, e1rm=e1rm, days_since=days)


POOL = [ex(n) for n in ["Barbell Bench Press", "Dumbbell Bench Press", "Assisted Dip", "Dumbbell Tricep Extension",
                        "Cable Tricep Pushdown", "Barbell Shoulder Press", "Dumbbell Lateral Raise", "Back Squat",
                        "Lat Pulldown", "Push Up"]]
CHEST = {"chest": 4, "triceps": 5, "shoulders": 2}


def plan(**kw):
    args = dict(pool=POOL, targets=CHEST, equipment=set(library.ALL_EQUIPMENT), minutes=45, goal="hypertrophy",
                variety=0.2, rng=random.Random(1))
    args.update(kw)
    return gen.generate(**args)


def test_equipment_is_respected():
    p = plan(equipment={"dumbbell", "bodyweight"})
    assert p and all(library.equipment_for(x["exercise"]) <= {"dumbbell", "bodyweight"} for x in p)


def test_stays_in_time_budget_and_scales_with_it():
    short, long = plan(minutes=20), plan(minutes=75)
    assert gen.estimated_minutes(short) <= 20 and gen.estimated_minutes(long) <= 75
    assert len(short) < len(long)


def test_only_trains_target_muscles_and_leads_with_compounds():
    p = plan()
    assert "Back Squat" not in [x["exercise"] for x in p] and "Lat Pulldown" not in [x["exercise"] for x in p]
    first_iso = next(i for i, x in enumerate(p) if not x["compound"])
    assert all(not x["compound"] for x in p[first_iso:])


def test_exclude_and_determinism():
    assert "Barbell Bench Press" not in [x["exercise"] for x in plan(exclude={"Barbell Bench Press"})]
    assert plan(variety=0, rng=random.Random(1)) == plan(variety=0, rng=random.Random(99))


def test_goal_changes_rep_ranges():
    strength, endurance = plan(goal="strength"), plan(goal="endurance")
    assert strength[0]["reps"] < endurance[0]["reps"] and strength[0]["rest_seconds"] > endurance[0]["rest_seconds"]


def test_weights_from_e1rm_new_and_bodyweight_exercises():
    assert gen.weight_for(100, 8, 0) == 75 and gen.weight_for(100, 8, 60) == 60 and gen.weight_for(None, 8, 0) == 0
    new = gen.plan_exercise(ex("Chest Press Machine", count=0, e1rm=None), "hypertrophy")
    assert new["weight_kg"] == 0 and "New for you" in new["reason"]
    assert gen.plan_exercise(ex("Push Up"), "hypertrophy")["weight_kg"] == 0


def test_first_heavy_compound_gets_a_warmup():
    p = plan()
    assert "Warm-up" in p[0].get("warmup", "") and all("warmup" not in x for x in p[1:])


def test_equipment_and_compound_tags():
    assert library.equipment_for("Back Squat") == {"barbell"} and library.equipment_for("Cable Row") == {"cable"}
    assert library.equipment_for("Mini Loop Band Tricep Press") == {"band"} and library.equipment_for("Plank") == {"bodyweight"}
    assert library.is_compound("Barbell Bench Press") and not library.is_compound("Dumbbell Tricep Extension")


# ---- API ----
import pytest  # noqa: E402


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """An empty database, for tests whose result depends on everything else in it."""
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "fresh.db"))
    app.init_db()


def add_history(exercise, n, when, reps=8, kg=40):
    with app.db() as con:
        for i in range(n):
            t = (when - timedelta(days=7 * i)).isoformat(timespec="seconds")
            sid = con.execute("INSERT INTO sessions (name,started_at,finished_at,source) VALUES ('h',?,?,'test')", (t, t)).lastrowid
            for k in range(3):
                con.execute("INSERT INTO session_sets (session_id,exercise,set_index,reps,weight_kg,completed_at) VALUES (?,?,?,?,?,?)",
                            (sid, exercise, k + 1, reps, kg, t))


def test_profiles_crud_and_validation():
    p = c.post("/equipment-profiles", headers=H, json={"name": "Garage", "equipment": ["barbell", "bodyweight"]}).json()
    assert c.post("/equipment-profiles", headers=H, json={"name": "Garage", "equipment": []}).status_code == 409
    assert c.post("/equipment-profiles", headers=H, json={"name": "X", "equipment": ["laser"]}).status_code == 422
    assert c.put(f"/equipment-profiles/{p['id']}", headers=H, json={"name": "Garage", "equipment": ["dumbbell"]}).json()["equipment"] == ["dumbbell"]
    assert c.delete(f"/equipment-profiles/{p['id']}", headers=H).status_code == 204
    assert {"Full gym", "Dumbbells only"} <= {x["name"] for x in c.get("/equipment-profiles", headers=H).json()}


def test_profiles_derive_from_history(fresh_db):
    now = datetime.now(timezone.utc)
    add_history("Barbell Bench Press", 4, now)
    add_history("Cable Tricep Pushdown", 4, now - timedelta(days=800))       # used, but long ago
    add_history("Kettlebell Swing", 1, now - timedelta(days=900))            # too little to count
    got = {p["name"]: p["equipment"] for p in c.post("/equipment-profiles/derive", headers=H).json()}
    assert got["From my history"] == ["barbell", "bodyweight", "cable"]
    assert got["Recent training"] == ["barbell", "bodyweight"]


def test_generate_endpoint():
    c.post("/templates", headers=H, json={"name": "Gen Chest", "exercises": [
        {"exercise": "Barbell Bench Press", "sets": 4, "reps": 8}, {"exercise": "Dumbbell Tricep Extension", "sets": 3, "reps": 10}]})
    add_history("Dumbbell Bench Press", 3, datetime.now(timezone.utc))
    r = c.post("/generate", headers=H, json={"template": "Gen Chest", "profile": "Dumbbells only", "seed": 1, "minutes": 40})
    assert r.status_code == 200
    j = r.json()
    assert j["equipment_profile"] == "Dumbbells only" and j["estimated_minutes"] <= 40 and j["exercises"]
    assert all(library.equipment_for(x["exercise"]) <= {"dumbbell", "bodyweight"} for x in j["exercises"])
    assert c.post("/generate", headers=H, json={"template": "Gen Chest", "seed": 1}).json() == \
        c.post("/generate", headers=H, json={"template": "Gen Chest", "seed": 1}).json()
    assert c.post("/generate", headers=H, json={"muscles": ["biceps"]}).json()["exercises"]
    assert c.post("/generate", headers=H, json={"profile": "Nope", "muscles": ["chest"]}).status_code == 404
    assert c.post("/generate", headers=H, json={"goal": "gains", "muscles": ["chest"]}).status_code == 422
    assert c.post("/generate", headers=H, json={"template": "Nope"}).status_code == 404
    assert c.post("/generate", headers=H, json={"muscles": ["elbows"]}).status_code == 422


def test_automatic_pick_avoids_the_day_you_just_trained(fresh_db):
    c.post("/templates", headers=H, json={"name": "Legs", "exercises": [
        {"exercise": "Back Squat", "sets": 4, "reps": 5}, {"exercise": "Lying Hamstrings Curl", "sets": 3, "reps": 10}]})
    c.post("/templates", headers=H, json={"name": "Chest", "exercises": [
        {"exercise": "Barbell Bench Press", "sets": 4, "reps": 8}, {"exercise": "Dumbbell Tricep Extension", "sets": 3, "reps": 10}]})
    add_history("Back Squat", 1, datetime.now(timezone.utc) - timedelta(hours=2), reps=5, kg=100)
    g = c.post("/generate", headers=H, json={}).json()
    assert g["name"].startswith("Chest") and all("Squat" not in x["exercise"] for x in g["exercises"])
    assert c.post("/generate", headers=H, json={"template": "Legs"}).json()["name"].startswith("Legs")  # but you can insist


def test_custom_session_swap_and_alternatives():
    body = {"name": "Mine", "source": "phone", "exercises": [
        {"exercise": "Barbell Bench Press", "sets": 3, "reps": 8, "weight_kg": 50},
        {"exercise": "Dumbbell Tricep Extension", "sets": 3, "reps": 12, "weight_kg": 10}]}
    s = c.post("/sessions/custom", headers=H, json=body).json()
    assert s["exercises"][0]["weight_kg"] == 50 and s["exercises"][0]["suggestion"] is None   # your plan is kept as given
    assert c.get("/sessions/active", headers=H).json()["id"] == s["id"]
    alts = [a["exercise"] for a in c.get("/exercises/Barbell Bench Press/alternatives", params={"profile": "Dumbbells only"}, headers=H).json()]
    assert "Dumbbell Bench Press" in alts and "Barbell Bench Press" not in alts
    sw = c.post(f"/sessions/{s['id']}/swap", headers=H, json={"exercise": "Barbell Bench Press", "replacement": "Dumbbell Bench Press"}).json()
    assert [e["exercise"] for e in sw["exercises"]][0] == "Dumbbell Bench Press" and sw["exercises"][0]["weight_kg"] > 0
    assert c.post(f"/sessions/{s['id']}/swap", headers=H, json={"exercise": "Dumbbell Bench Press", "replacement": "Dumbbell Tricep Extension"}).status_code == 409
    assert c.post(f"/sessions/{s['id']}/swap", headers=H, json={"exercise": "Dumbbell Tricep Extension", "replacement": "Zzz Nonsense"}).status_code == 422
    c.post(f"/sessions/{s['id']}/sets", headers=H, json={"exercise": "Dumbbell Bench Press", "set_index": 1, "reps": 8, "weight_kg": 20})
    assert c.post(f"/sessions/{s['id']}/swap", headers=H, json={"exercise": "Dumbbell Bench Press", "replacement": "Chest Press Machine"}).status_code == 409
    assert c.post("/sessions/custom", headers=H, json={"name": "Empty", "exercises": []}).status_code == 422
