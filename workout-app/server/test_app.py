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
