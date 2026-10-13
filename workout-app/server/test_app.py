import os
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["API_TOKEN"] = "secret"

from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402

c = TestClient(app.app)
H = {"Authorization": "Bearer secret"}
LEGS = {"name": "Legs", "exercises": [{"exercise": "Back Squat", "sets": 3, "reps": 5, "weight_kg": 65.8},
                                      {"exercise": "Deadlift", "sets": 3, "reps": 5, "weight_kg": 90.7}]}


def test_auth_required():
    assert c.get("/templates").status_code == 401
    assert c.get("/templates", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_template_crud():
    t = c.post("/templates", json=LEGS, headers=H).json()
    assert [e["exercise"] for e in t["exercises"]] == ["Back Squat", "Deadlift"]
    upd = dict(LEGS, exercises=LEGS["exercises"][:1])
    assert len(c.put(f"/templates/{t['id']}", json=upd, headers=H).json()["exercises"]) == 1
    assert c.put("/templates/999", json=upd, headers=H).status_code == 404


def test_session_flow():
    tid = c.post("/templates", json=LEGS, headers=H).json()["id"]
    assert c.get("/sessions/active", headers=H).status_code in (200, 404)
    s1 = c.post("/sessions", json={"template_id": tid, "source": "discord"}, headers=H).json()
    assert s1["source"] == "discord" and len(s1["exercises"]) == 2
    assert c.get("/sessions/active", headers=H).json()["id"] == s1["id"]
    # starting another closes the first, so only one session is ever active
    s2 = c.post("/sessions", json={"template_id": tid, "source": "watch"}, headers=H).json()
    assert c.get("/sessions/active", headers=H).json()["id"] == s2["id"]
    st = {"exercise": "Back Squat", "set_index": 1, "reps": 5, "weight_kg": 65.8}
    assert len(c.post(f"/sessions/{s2['id']}/sets", json=st, headers=H).json()["completed_sets"]) == 1
    assert c.post(f"/sessions/{s1['id']}/sets", json=st, headers=H).status_code == 409
    assert c.post(f"/sessions/{s2['id']}/finish", headers=H).json()["finished_at"]
    assert c.get("/sessions/active", headers=H).status_code == 404


def test_template_edit_does_not_change_past_sessions():
    tid = c.post("/templates", json=LEGS, headers=H).json()["id"]
    s = c.post("/sessions", json={"template_id": tid}, headers=H).json()
    c.put(f"/templates/{tid}", json=dict(LEGS, exercises=LEGS["exercises"][:1]), headers=H)
    assert len(c.get("/sessions/active", headers=H).json()["exercises"]) == 2 == len(s["exercises"])


def _start_legs():
    tid = c.post("/templates", json=LEGS, headers=H).json()["id"]
    return c.post("/sessions", json={"template_id": tid}, headers=H).json()


def test_log_actual_values_edit_and_delete():
    s = _start_legs()
    out = c.post(f"/sessions/{s['id']}/sets", headers=H,
                 json={"exercise": "Back Squat", "set_index": 1, "reps": 6, "weight_kg": 70}).json()
    st = out["completed_sets"][0]
    assert (st["reps"], st["weight_kg"], st["is_warmup"]) == (6, 70, False)
    out = c.patch(f"/sessions/{s['id']}/sets/{st['id']}", json={"reps": 5}, headers=H).json()
    assert out["completed_sets"][0]["reps"] == 5 and out["completed_sets"][0]["weight_kg"] == 70
    assert c.delete(f"/sessions/{s['id']}/sets/{st['id']}", headers=H).json()["completed_sets"] == []
    assert c.delete(f"/sessions/{s['id']}/sets/{st['id']}", headers=H).status_code == 404


def test_rest_seconds_default_and_custom():
    t = c.post("/templates", headers=H, json={"name": "R", "exercises": [
        {"exercise": "A", "sets": 3, "reps": 5}, {"exercise": "B", "sets": 3, "reps": 5, "rest_seconds": 180}]}).json()
    assert [e["rest_seconds"] for e in t["exercises"]] == [90, 180]
    s = c.post("/sessions", json={"template_id": t["id"]}, headers=H).json()
    assert [e["rest_seconds"] for e in s["exercises"]] == [90, 180]


def test_last_performance_prefills_next_session_and_ignores_warmups():
    s1 = _start_legs()
    for i, (r, w, wu) in enumerate([(10, 20, True), (5, 100, False), (5, 100, False)], 1):
        c.post(f"/sessions/{s1['id']}/sets", headers=H,
               json={"exercise": "Back Squat", "set_index": i, "reps": r, "weight_kg": w, "is_warmup": wu})
    c.post(f"/sessions/{s1['id']}/finish", headers=H)
    s2 = _start_legs()
    squat = next(e for e in s2["exercises"] if e["exercise"] == "Back Squat")
    assert squat["last"]["sets"] == [{"reps": 5, "weight_kg": 100}, {"reps": 5, "weight_kg": 100}]
    assert next(e for e in s2["exercises"] if e["exercise"] == "Deadlift")["last"] is None


def test_exercise_history_and_summary():
    ex = {e["exercise"]: e for e in c.get("/exercises", headers=H).json()}
    assert ex["Back Squat"]["best_e1rm_kg"] == round(100 * (1 + 5 / 30), 1)
    h = c.get("/exercises/Back Squat/history", headers=H).json()
    assert h[0]["sets"][0] == {"reps": 5, "weight_kg": 100} and h[0]["best_e1rm_kg"] == 116.7


def test_import_history_is_idempotent(tmp_path):
    import import_history as ih
    csvp = tmp_path / "h.csv"
    csvp.write_text("Date,Exercise,Reps,Weight(kg),Duration(s),Distance(m),Incline,Resistance,isWarmup,Note,multiplier\n"
                    "2019-03-01 10:00:00 +0000,Barbell Bench Press, 8,40.0,0,0,0,0,true,, 0\n"
                    "2019-03-01 10:05:00 +0000,Barbell Bench Press, 5,60.0,0,0,0,0,false,, 0\n"
                    "2019-03-01 10:10:00 +0000,Dumbbell Tricep Extension, 8,15.0,0,0,0,0,false,, 0\n"
                    "2019-03-01 11:00:00 +0000,Running, 0,0.0,600,2000,0,0,false,, 0\n")
    assert ih.import_days(ih.load(str(csvp))) == (1, 0)
    assert ih.import_days(ih.load(str(csvp))) == (0, 1)
    sess = [s for s in c.get("/sessions?limit=100", headers=H).json() if s["source"] == "import"][0]
    assert sess["name"] == "Chest & Triceps" and len(sess["completed_sets"]) == 3  # cardio row ignored
    assert [s["is_warmup"] for s in sess["completed_sets"]] == [True, False, False]
    assert c.get("/sessions/active", headers=H).status_code in (200, 404)  # imported sessions are never "active"


def test_health_summary_is_stored_merged_and_validated():
    s = _start_legs()
    assert s["health"] is None
    out = c.post(f"/sessions/{s['id']}/health", headers=H,
                 json={"avg_heart_rate": 118.5, "max_heart_rate": 162, "active_calories": 240.4}).json()
    assert out["health"]["avg_heart_rate"] == 118.5 and out["health"]["healthkit_uuid"] is None
    out = c.post(f"/sessions/{s['id']}/health", headers=H, json={"duration_seconds": 3100, "healthkit_uuid": "ABC"}).json()
    assert out["health"]["avg_heart_rate"] == 118.5 and out["health"]["duration_seconds"] == 3100   # earlier fields kept
    c.post(f"/sessions/{s['id']}/finish", headers=H)
    assert c.post(f"/sessions/{s['id']}/health", headers=H, json={"active_calories": 250}).json()["health"]["active_calories"] == 250
    assert c.post(f"/sessions/{s['id']}/health", headers=H, json={"avg_heart_rate": 5}).status_code == 422
    assert c.post("/sessions/99999/health", headers=H, json={"active_calories": 1}).status_code == 404
    listed = [x for x in c.get("/sessions?limit=50", headers=H).json() if x["id"] == s["id"]][0]
    assert listed["health"]["max_heart_rate"] == 162
