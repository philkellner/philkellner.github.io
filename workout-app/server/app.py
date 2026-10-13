"""Workout API shared by the iPhone app, Apple Watch app and Discord coach.

Auth: every request needs `Authorization: Bearer $API_TOKEN`.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

DB_PATH = os.getenv("DB_PATH", "workouts.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS templates (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS template_exercises (
  id INTEGER PRIMARY KEY, template_id INTEGER NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
  position INTEGER NOT NULL, exercise TEXT NOT NULL, sets INTEGER NOT NULL, reps INTEGER NOT NULL,
  weight_kg REAL NOT NULL DEFAULT 0, rest_seconds INTEGER NOT NULL DEFAULT 90);
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY, template_id INTEGER REFERENCES templates(id) ON DELETE SET NULL,
  name TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, source TEXT NOT NULL DEFAULT 'api');
CREATE TABLE IF NOT EXISTS session_exercises (
  id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  position INTEGER NOT NULL, exercise TEXT NOT NULL, sets INTEGER NOT NULL, reps INTEGER NOT NULL,
  weight_kg REAL NOT NULL DEFAULT 0, rest_seconds INTEGER NOT NULL DEFAULT 90);
CREATE TABLE IF NOT EXISTS session_sets (
  id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  exercise TEXT NOT NULL, set_index INTEGER NOT NULL, reps INTEGER NOT NULL, weight_kg REAL NOT NULL,
  completed_at TEXT NOT NULL, is_warmup INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_sets_exercise ON session_sets(exercise);
"""

# columns added after the first release; applied to databases created by an older version
MIGRATIONS = [("template_exercises", "rest_seconds", "INTEGER NOT NULL DEFAULT 90"),
              ("session_exercises", "rest_seconds", "INTEGER NOT NULL DEFAULT 90"),
              ("session_sets", "is_warmup", "INTEGER NOT NULL DEFAULT 0")]


@contextmanager
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    with db() as con:
        con.executescript(SCHEMA)
        for table, col, decl in MIGRATIONS:
            if col not in {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def require_token(authorization: str = Header(default="")):
    token = os.getenv("API_TOKEN")
    if not token:
        raise HTTPException(500, "API_TOKEN is not configured")
    if authorization != f"Bearer {token}":
        raise HTTPException(401, "invalid token")


app = FastAPI(title="Workout API", dependencies=[Depends(require_token)])


class ExerciseIn(BaseModel):
    exercise: str = Field(min_length=1)
    sets: int = Field(ge=1, le=20)
    reps: int = Field(ge=1, le=100)
    weight_kg: float = Field(default=0, ge=0)
    rest_seconds: int = Field(default=90, ge=0, le=900)


class TemplateIn(BaseModel):
    name: str = Field(min_length=1)
    exercises: list[ExerciseIn]


class SetIn(BaseModel):
    exercise: str
    set_index: int = Field(ge=1)
    reps: int = Field(ge=0)
    weight_kg: float = Field(ge=0)
    is_warmup: bool = False


class SetPatch(BaseModel):
    reps: int | None = Field(default=None, ge=0)
    weight_kg: float | None = Field(default=None, ge=0)


class SessionStart(BaseModel):
    template_id: int
    source: str = "api"  # "watch", "phone", "discord"


def template_out(con, row):
    ex = con.execute("SELECT exercise,sets,reps,weight_kg,rest_seconds FROM template_exercises WHERE template_id=? ORDER BY position",
                     (row["id"],)).fetchall()
    return {"id": row["id"], "name": row["name"], "exercises": [dict(e) for e in ex]}


def e1rm(weight_kg, reps):
    """Epley estimated one-rep max; only meaningful for loaded sets of up to 12 reps."""
    return round(weight_kg * (1 + reps / 30), 1) if weight_kg > 0 and 0 < reps <= 12 else 0.0


def last_performance(con, exercise, before=None):
    """Working sets from the most recent earlier session that included this exercise (for prefilling)."""
    row = con.execute("SELECT s.id, s.started_at FROM sessions s JOIN session_sets t ON t.session_id=s.id "
                      "WHERE t.exercise=? AND t.is_warmup=0 AND s.id != COALESCE(?,-1) "
                      "ORDER BY s.started_at DESC, s.id DESC LIMIT 1", (exercise, before)).fetchone()
    if not row:
        return None
    sets = con.execute("SELECT reps,weight_kg FROM session_sets WHERE session_id=? AND exercise=? AND is_warmup=0 "
                       "ORDER BY id", (row["id"], exercise)).fetchall()
    return {"date": row["started_at"], "sets": [dict(x) for x in sets]}


def session_out(con, row):
    ex = [dict(e) for e in con.execute(
        "SELECT exercise,sets,reps,weight_kg,rest_seconds FROM session_exercises WHERE session_id=? ORDER BY position",
        (row["id"],))]
    for e in ex:
        e["last"] = last_performance(con, e["exercise"], row["id"])
    sets = con.execute("SELECT id,exercise,set_index,reps,weight_kg,is_warmup,completed_at FROM session_sets "
                       "WHERE session_id=? ORDER BY id", (row["id"],)).fetchall()
    return {"id": row["id"], "template_id": row["template_id"], "name": row["name"], "started_at": row["started_at"],
            "finished_at": row["finished_at"], "source": row["source"], "exercises": ex,
            "completed_sets": [dict(x, is_warmup=bool(x["is_warmup"])) for x in sets]}


def write_exercises(con, table, key, key_id, exercises):
    for i, e in enumerate(exercises):
        con.execute(f"INSERT INTO {table} ({key},position,exercise,sets,reps,weight_kg,rest_seconds) "
                    "VALUES (?,?,?,?,?,?,?)", (key_id, i, e.exercise, e.sets, e.reps, e.weight_kg, e.rest_seconds))


@app.get("/templates")
def list_templates():
    with db() as con:
        return [template_out(con, r) for r in con.execute("SELECT * FROM templates ORDER BY position,id")]


@app.post("/templates", status_code=201)
def create_template(t: TemplateIn):
    with db() as con:
        pos = con.execute("SELECT COALESCE(MAX(position),-1)+1 FROM templates").fetchone()[0]
        tid = con.execute("INSERT INTO templates (name,position) VALUES (?,?)", (t.name, pos)).lastrowid
        write_exercises(con, "template_exercises", "template_id", tid, t.exercises)
        return template_out(con, con.execute("SELECT * FROM templates WHERE id=?", (tid,)).fetchone())


@app.put("/templates/{tid}")
def update_template(tid: int, t: TemplateIn):
    with db() as con:
        if not con.execute("SELECT 1 FROM templates WHERE id=?", (tid,)).fetchone():
            raise HTTPException(404, "template not found")
        con.execute("UPDATE templates SET name=? WHERE id=?", (t.name, tid))
        con.execute("DELETE FROM template_exercises WHERE template_id=?", (tid,))
        write_exercises(con, "template_exercises", "template_id", tid, t.exercises)
        return template_out(con, con.execute("SELECT * FROM templates WHERE id=?", (tid,)).fetchone())


@app.delete("/templates/{tid}", status_code=204)
def delete_template(tid: int):
    with db() as con:
        con.execute("DELETE FROM templates WHERE id=?", (tid,))


@app.post("/sessions", status_code=201)
def start_session(s: SessionStart):
    """Start a workout from a template. Any still-open session is finished first so only one is ever active."""
    with db() as con:
        t = con.execute("SELECT * FROM templates WHERE id=?", (s.template_id,)).fetchone()
        if not t:
            raise HTTPException(404, "template not found")
        con.execute("UPDATE sessions SET finished_at=? WHERE finished_at IS NULL", (now(),))
        sid = con.execute("INSERT INTO sessions (template_id,name,started_at,source) VALUES (?,?,?,?)",
                          (t["id"], t["name"], now(), s.source)).lastrowid
        con.execute("INSERT INTO session_exercises (session_id,position,exercise,sets,reps,weight_kg,rest_seconds) "
                    "SELECT ?,position,exercise,sets,reps,weight_kg,rest_seconds FROM template_exercises WHERE template_id=?",
                    (sid, t["id"]))
        return session_out(con, con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone())


@app.get("/sessions/active")
def active_session():
    """What the Watch polls: the in-progress workout, or 404 when nothing is running."""
    with db() as con:
        row = con.execute("SELECT * FROM sessions WHERE finished_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            raise HTTPException(404, "no active session")
        return session_out(con, row)


@app.get("/sessions")
def list_sessions(limit: int = 20):
    with db() as con:
        rows = con.execute("SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (min(limit, 100),)).fetchall()
        return [session_out(con, r) for r in rows]


@app.post("/sessions/{sid}/sets", status_code=201)
def log_set(sid: int, s: SetIn):
    with db() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404, "session not found")
        if row["finished_at"]:
            raise HTTPException(409, "session already finished")
        con.execute("INSERT INTO session_sets (session_id,exercise,set_index,reps,weight_kg,completed_at,is_warmup) "
                    "VALUES (?,?,?,?,?,?,?)", (sid, s.exercise, s.set_index, s.reps, s.weight_kg, now(), int(s.is_warmup)))
        return session_out(con, row)


@app.patch("/sessions/{sid}/sets/{set_id}")
def edit_set(sid: int, set_id: int, p: SetPatch):
    with db() as con:
        t = con.execute("SELECT * FROM session_sets WHERE id=? AND session_id=?", (set_id, sid)).fetchone()
        if not t:
            raise HTTPException(404, "set not found")
        con.execute("UPDATE session_sets SET reps=?, weight_kg=? WHERE id=?",
                    (t["reps"] if p.reps is None else p.reps, t["weight_kg"] if p.weight_kg is None else p.weight_kg, set_id))
        return session_out(con, con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone())


@app.delete("/sessions/{sid}/sets/{set_id}")
def delete_set(sid: int, set_id: int):
    with db() as con:
        if not con.execute("SELECT 1 FROM session_sets WHERE id=? AND session_id=?", (set_id, sid)).fetchone():
            raise HTTPException(404, "set not found")
        con.execute("DELETE FROM session_sets WHERE id=?", (set_id,))
        return session_out(con, con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone())


@app.get("/exercises")
def list_exercises():
    """Every exercise you've logged working sets for, with session count and best estimated 1RM."""
    with db() as con:
        rows = con.execute("SELECT t.exercise, t.reps, t.weight_kg, s.id sid, s.started_at FROM session_sets t "
                           "JOIN sessions s ON s.id=t.session_id WHERE t.is_warmup=0").fetchall()
    agg = {}
    for r in rows:
        a = agg.setdefault(r["exercise"], {"exercise": r["exercise"], "sessions": set(), "best_e1rm_kg": 0.0, "last_date": ""})
        a["sessions"].add(r["sid"])
        a["best_e1rm_kg"] = max(a["best_e1rm_kg"], e1rm(r["weight_kg"], r["reps"]))
        a["last_date"] = max(a["last_date"], r["started_at"])
    out = [dict(a, sessions=len(a["sessions"])) for a in agg.values()]
    return sorted(out, key=lambda a: (-a["sessions"], a["exercise"]))


@app.get("/exercises/{name:path}/history")
def exercise_history(name: str, limit: int = 30):
    """Newest-first list of sessions for one exercise, with each session's sets and best estimated 1RM."""
    with db() as con:
        rows = con.execute("SELECT s.id sid, s.started_at, t.reps, t.weight_kg FROM session_sets t "
                           "JOIN sessions s ON s.id=t.session_id WHERE t.exercise=? AND t.is_warmup=0 "
                           "ORDER BY s.started_at DESC, s.id DESC, t.id", (name,)).fetchall()
    sessions = {}
    for r in rows:
        s = sessions.setdefault(r["sid"], {"session_id": r["sid"], "date": r["started_at"], "sets": [], "best_e1rm_kg": 0.0})
        s["sets"].append({"reps": r["reps"], "weight_kg": r["weight_kg"]})
        s["best_e1rm_kg"] = max(s["best_e1rm_kg"], e1rm(r["weight_kg"], r["reps"]))
    return list(sessions.values())[:min(limit, 200)]


@app.post("/sessions/{sid}/finish")
def finish_session(sid: int):
    with db() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404, "session not found")
        if not row["finished_at"]:
            con.execute("UPDATE sessions SET finished_at=? WHERE id=?", (now(), sid))
        return session_out(con, con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone())


init_db()
