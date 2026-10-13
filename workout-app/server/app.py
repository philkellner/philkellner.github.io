"""Workout API shared by the iPhone app, Apple Watch app and Discord coach.

Auth: every request needs `Authorization: Bearer $API_TOKEN`.
"""
import json
import os
import random
import sqlite3
import statistics
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

import cues
import generator
import library
import media
import progression
import recovery as recovery_model

DB_PATH = os.getenv("DB_PATH", "workouts.db")
MEDIA_DIR = os.getenv("MEDIA_DIR", "media")

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
CREATE TABLE IF NOT EXISTS equipment_profiles (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, equipment TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exercise_media (
  exercise TEXT PRIMARY KEY, video_file TEXT, youtube TEXT NOT NULL DEFAULT '[]');
CREATE INDEX IF NOT EXISTS idx_sets_exercise ON session_sets(exercise);
"""

# columns added after the first release; applied to databases created by an older version
MIGRATIONS = [("template_exercises", "rest_seconds", "INTEGER NOT NULL DEFAULT 90"),
              ("session_exercises", "rest_seconds", "INTEGER NOT NULL DEFAULT 90"),
              ("session_sets", "is_warmup", "INTEGER NOT NULL DEFAULT 0"),
              ("sessions", "custom", "INTEGER NOT NULL DEFAULT 0"),
              ("sessions", "avg_heart_rate", "REAL"), ("sessions", "max_heart_rate", "REAL"),
              ("sessions", "active_calories", "REAL"), ("sessions", "duration_seconds", "INTEGER"),
              ("sessions", "healthkit_uuid", "TEXT")]


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
        if not con.execute("SELECT 1 FROM equipment_profiles").fetchone():
            for name, eq in [("Full gym", library.ALL_EQUIPMENT), ("Dumbbells only", ["dumbbell", "bodyweight"]),
                             ("Bodyweight & bands", ["bodyweight", "band"])]:
                con.execute("INSERT INTO equipment_profiles (name,equipment) VALUES (?,?)", (name, ",".join(eq)))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def require_token(request: Request, authorization: str = Header(default="")):
    if request.url.path.startswith("/media/"):
        return          # media links carry their own signature (see media.py)
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
    return {"date": row["started_at"], "sets": [dict(x) for x in sets], "session_id": row["id"]}


def parse_ts(s):
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def suggestion_for(con, exercise, before=None, as_of=None):
    """Next-session weight/reps for an exercise from its logged history, or None for a new exercise."""
    rows = con.execute("SELECT s.id, s.started_at, s.source FROM sessions s WHERE s.id != COALESCE(?,-1) AND EXISTS "
                       "(SELECT 1 FROM session_sets t WHERE t.session_id=s.id AND t.exercise=? AND t.is_warmup=0) "
                       "ORDER BY s.started_at DESC, s.id DESC LIMIT 4", (before, exercise)).fetchall()
    sessions = []
    for r in rows:
        sets = con.execute("SELECT reps,weight_kg FROM session_sets WHERE session_id=? AND exercise=? AND is_warmup=0 "
                           "ORDER BY id", (r["id"], exercise)).fetchall()
        sessions.append({"id": r["id"], "source": r["source"], "date": parse_ts(r["started_at"]), "sets": [dict(x) for x in sets]})
    if not sessions:
        return None
    plan = con.execute("SELECT sets,reps FROM session_exercises WHERE session_id=? AND exercise=?",
                       (sessions[0]["id"], exercise)).fetchone()
    goal_sets = plan["sets"] if plan else len(sessions[0]["sets"])
    if plan and sessions[0]["source"] != "import":
        goal_reps = plan["reps"]  # a deliberate target from a template-driven workout
    else:
        # imported history has no plan: use your typical reps over recent sessions, not one good or bad day
        typical = sorted(statistics.median(x["reps"] for x in s["sets"]) for s in sessions)
        goal_reps = max(1, round(typical[len(typical) // 2]))
    return progression.suggest(exercise, sessions, goal_sets, goal_reps, as_of or datetime.now(timezone.utc))


def session_out(con, row):
    ex = [dict(e) for e in con.execute(
        "SELECT exercise,sets,reps,weight_kg,rest_seconds FROM session_exercises WHERE session_id=? ORDER BY position",
        (row["id"],))]
    for e in ex:
        live = row["finished_at"] is None
        e["last"] = last_performance(con, e["exercise"], row["id"]) if live else None
        e["suggestion"] = suggestion_for(con, e["exercise"], row["id"]) if live and not row["custom"] else None
    sets = con.execute("SELECT id,exercise,set_index,reps,weight_kg,is_warmup,completed_at FROM session_sets "
                       "WHERE session_id=? ORDER BY id", (row["id"],)).fetchall()
    health = {k: row[k] for k in ("avg_heart_rate", "max_heart_rate", "active_calories", "duration_seconds", "healthkit_uuid")}
    return {"id": row["id"], "template_id": row["template_id"], "name": row["name"], "started_at": row["started_at"],
            "finished_at": row["finished_at"], "source": row["source"], "exercises": ex,
            "health": health if any(v is not None for v in health.values()) else None,
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
        for e in con.execute("SELECT id, exercise FROM session_exercises WHERE session_id=?", (sid,)).fetchall():
            sug = suggestion_for(con, e["exercise"], sid)
            if sug:
                con.execute("UPDATE session_exercises SET weight_kg=?, reps=? WHERE id=?", (sug["weight_kg"], sug["reps"], e["id"]))
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


@app.get("/exercises/{name:path}/suggestion")
def exercise_suggestion(name: str):
    """What to lift next time for this exercise, with the reason."""
    with db() as con:
        sug = suggestion_for(con, name)
    if not sug:
        raise HTTPException(404, "no history for this exercise")
    return sug


def recovery_rows(con, as_of):
    since = (as_of - timedelta(days=10)).isoformat(timespec="seconds")
    rows = con.execute("SELECT session_id, exercise, completed_at FROM session_sets WHERE is_warmup=0 AND completed_at>=? "
                       "ORDER BY id", (since,)).fetchall()
    by_session = {}
    for r in rows:
        s = by_session.setdefault(r["session_id"], {"end": parse_ts(r["completed_at"]), "exercises": []})
        s["end"] = max(s["end"], parse_ts(r["completed_at"]))
        s["exercises"].append(r["exercise"])
    return recovery_model.recovery(list(by_session.values()), as_of)


def parse_as_of(as_of):
    try:
        return parse_ts(as_of) if as_of else datetime.now(timezone.utc)
    except ValueError:
        raise HTTPException(422, "as_of must be an ISO timestamp")


@app.get("/recovery")
def get_recovery(as_of: str | None = None):
    """Recovery per muscle, most fatigued first. `as_of` (ISO timestamp) asks "what will it look like then?"."""
    with db() as con:
        return recovery_rows(con, parse_as_of(as_of))


def get_recommendation_rows(con, rec):
    out = []
    for t in con.execute("SELECT * FROM templates ORDER BY position,id").fetchall():
        ex = [dict(e) for e in con.execute("SELECT exercise,sets FROM template_exercises WHERE template_id=?", (t["id"],))]
        out.append({"template_id": t["id"], "name": t["name"], **recovery_model.template_readiness(ex, rec)})
    return out


@app.get("/recommendation")
def get_recommendation(as_of: str | None = None):
    """Your templates ranked by how recovered the muscles they work are."""
    with db() as con:
        out = get_recommendation_rows(con, recovery_rows(con, parse_as_of(as_of)))
    out.sort(key=lambda r: -r["readiness"])
    for i, r in enumerate(out):
        r["recommended"] = i == 0
    return out


# ---------- equipment profiles ----------
class ProfileIn(BaseModel):
    name: str = Field(min_length=1)
    equipment: list[str]


def profile_out(r):
    return {"id": r["id"], "name": r["name"], "equipment": r["equipment"].split(",") if r["equipment"] else []}


def check_equipment(eq):
    bad = [e for e in eq if e not in library.ALL_EQUIPMENT]
    if bad:
        raise HTTPException(422, f"unknown equipment {bad}; choose from {library.ALL_EQUIPMENT}")


def derive_profiles(con):
    """Create/refresh profiles from the equipment your logs show you actually use."""
    rows = con.execute("SELECT exercise, COUNT(DISTINCT session_id) n, MAX(completed_at) last FROM session_sets "
                       "WHERE is_warmup=0 GROUP BY exercise").fetchall()
    if not rows:
        return []
    cutoff = (parse_ts(max(r["last"] for r in rows)) - timedelta(days=365)).isoformat(timespec="seconds")
    recent_rows = con.execute("SELECT exercise, COUNT(DISTINCT session_id) n FROM session_sets WHERE is_warmup=0 "
                              "AND completed_at>=? GROUP BY exercise", (cutoff,)).fetchall()
    def tags(rs):
        use = Counter()
        for r in rs:
            use[next(iter(library.equipment_for(r["exercise"])))] += r["n"]
        return sorted({t for t, n in use.items() if n >= 3} | {"bodyweight"})
    out = []
    for name, eq in [("From my history", tags(rows)), ("Recent training", tags(recent_rows))]:
        con.execute("INSERT INTO equipment_profiles (name,equipment) VALUES (?,?) "
                    "ON CONFLICT(name) DO UPDATE SET equipment=excluded.equipment", (name, ",".join(eq)))
        out.append(name)
    return out


@app.get("/equipment-profiles")
def list_profiles():
    with db() as con:
        return [profile_out(r) for r in con.execute("SELECT * FROM equipment_profiles ORDER BY id")]


@app.post("/equipment-profiles", status_code=201)
def create_profile(p: ProfileIn):
    check_equipment(p.equipment)
    with db() as con:
        try:
            pid = con.execute("INSERT INTO equipment_profiles (name,equipment) VALUES (?,?)",
                              (p.name, ",".join(p.equipment))).lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(409, "a profile with that name exists")
        return profile_out(con.execute("SELECT * FROM equipment_profiles WHERE id=?", (pid,)).fetchone())


@app.put("/equipment-profiles/{pid}")
def update_profile(pid: int, p: ProfileIn):
    check_equipment(p.equipment)
    with db() as con:
        if not con.execute("UPDATE equipment_profiles SET name=?, equipment=? WHERE id=?",
                           (p.name, ",".join(p.equipment), pid)).rowcount:
            raise HTTPException(404, "profile not found")
        return profile_out(con.execute("SELECT * FROM equipment_profiles WHERE id=?", (pid,)).fetchone())


@app.delete("/equipment-profiles/{pid}", status_code=204)
def delete_profile(pid: int):
    with db() as con:
        con.execute("DELETE FROM equipment_profiles WHERE id=?", (pid,))


@app.post("/equipment-profiles/derive")
def derive_profiles_endpoint():
    """Build "From my history" and "Recent training" profiles from the equipment you've logged."""
    with db() as con:
        names = derive_profiles(con)
        return [profile_out(r) for r in con.execute("SELECT * FROM equipment_profiles ORDER BY id") if r["name"] in names]


def get_profile(con, name):
    """Named profile, else "From my history", else "Full gym"."""
    for n in ([name] if name else []) + ["From my history", "Full gym"]:
        r = con.execute("SELECT * FROM equipment_profiles WHERE name=?", (n,)).fetchone()
        if r:
            return profile_out(r)
        if name and n == name:
            raise HTTPException(404, f"no equipment profile named {name!r}")


# ---------- generator, swaps, custom sessions ----------
def build_pool(con, as_of):
    """Every exercise worth offering: ones you've done at least twice, plus the built-in library."""
    stats = {}
    for r in con.execute("SELECT t.exercise, t.reps, t.weight_kg, s.id sid, s.started_at FROM session_sets t "
                         "JOIN sessions s ON s.id=t.session_id WHERE t.is_warmup=0"):
        sessions = stats.setdefault(r["exercise"], {})
        d = sessions.setdefault(r["sid"], {"date": r["started_at"], "e1rm": 0.0})
        d["e1rm"] = max(d["e1rm"], e1rm(r["weight_kg"], r["reps"]))
    pool = []
    for name in set(stats) | set(library.builtin_exercises()):
        meta = library.describe(name)
        sessions = stats.get(name, {})
        if not meta["primary"] or (len(sessions) < 2 and name not in library.builtin_exercises()):
            continue
        last = max(sessions.values(), key=lambda d: d["date"]) if sessions else None
        pool.append(dict(meta, count=len(sessions), e1rm=(last["e1rm"] or None) if last else None,
                         days_since=(as_of - parse_ts(last["date"])).days if last else 0))
    return sorted(pool, key=lambda c: c["exercise"])   # stable order so a seed reproduces the same workout


class GenerateIn(BaseModel):
    minutes: int = Field(default=45, ge=15, le=120)
    goal: str = "hypertrophy"
    profile: str | None = None            # equipment profile name; default: From my history
    template: str | None = None           # train the muscles of this template day
    muscles: list[str] | None = None      # or name muscles directly
    variety: float = Field(default=0.2, ge=0, le=1)   # 0 = stick to what you know, 1 = adventurous
    exclude: list[str] = []
    seed: int | None = None


@app.post("/generate")
def generate_workout(g: GenerateIn):
    """Draft a workout from recovery, equipment, time and goal. Nothing is saved until you start it."""
    if g.goal not in generator.GOALS:
        raise HTTPException(422, f"goal must be one of {list(generator.GOALS)}")
    as_of = datetime.now(timezone.utc)
    with db() as con:
        profile = get_profile(con, g.profile)
        rec = recovery_rows(con, as_of)
        pct = {r["muscle"]: r["recovery_pct"] for r in rec}
        if g.muscles:
            bad = [m for m in g.muscles if m not in pct]
            if bad:
                raise HTTPException(422, f"unknown muscles {bad}")
            targets, label = {m: 1.0 for m in g.muscles}, ", ".join(g.muscles)
        else:
            templates = {t["name"]: t for t in con.execute("SELECT * FROM templates")}
            if g.template:
                t = templates.get(g.template)
                if not t:
                    raise HTTPException(404, f"no template named {g.template!r}")
            else:
                ready = {x["name"]: x["readiness"] for x in (get_recommendation_rows(con, rec))}
                if not ready:
                    raise HTTPException(409, "no templates to base the workout on; pass `muscles`")
                t = templates[max(ready, key=ready.get)]
            ex = [dict(e) for e in con.execute("SELECT exercise,sets FROM template_exercises WHERE template_id=?", (t["id"],))]
            targets, label = recovery_model.template_loads(ex), t["name"]
            if not g.template:   # automatic pick: leave out muscles that are still sore
                fresh = {m: v for m, v in targets.items() if pct[m] >= 50}
                targets = fresh or targets
        pool = build_pool(con, as_of)
    rng = random.Random(g.seed if g.seed is not None else as_of.toordinal())
    plan = generator.generate(pool, targets, set(profile["equipment"]), g.minutes, g.goal, g.variety, rng, set(g.exclude))
    if not plan:
        raise HTTPException(409, "no exercises fit; try more time or a bigger equipment profile")
    return {"name": f"{label} ({g.goal})", "goal": g.goal, "minutes": g.minutes,
            "estimated_minutes": generator.estimated_minutes(plan), "equipment_profile": profile["name"],
            "targets": {m: pct[m] for m in sorted(targets, key=lambda m: -targets[m])}, "exercises": plan}


class CustomSession(BaseModel):
    name: str = Field(min_length=1)
    exercises: list[ExerciseIn] = Field(min_length=1)
    source: str = "api"


@app.post("/sessions/custom", status_code=201)
def start_custom_session(c: CustomSession):
    """Start a workout from an explicit exercise list (e.g. a generated draft). The plan is used as given."""
    with db() as con:
        con.execute("UPDATE sessions SET finished_at=? WHERE finished_at IS NULL", (now(),))
        sid = con.execute("INSERT INTO sessions (template_id,name,started_at,source,custom) VALUES (NULL,?,?,?,1)",
                          (c.name, now(), c.source)).lastrowid
        write_exercises(con, "session_exercises", "session_id", sid, c.exercises)
        return session_out(con, con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone())


@app.get("/exercises/{name:path}/alternatives")
def exercise_alternatives(name: str, profile: str | None = None):
    """Swap candidates: same main muscles, equipment you have, most familiar first."""
    with db() as con:
        eq = set(get_profile(con, profile)["equipment"])
        pool = build_pool(con, datetime.now(timezone.utc))
    me = library.describe(name)
    out = [c for c in pool if c["exercise"] != name and c["equipment"] <= eq and set(c["primary"]) & set(me["primary"])]
    out.sort(key=lambda c: (c["compound"] != me["compound"], -len(set(c["primary"]) & set(me["primary"])), -c["count"], c["exercise"]))
    return [{"exercise": c["exercise"], "equipment": sorted(c["equipment"]), "sessions": c["count"]} for c in out[:8]]


class SwapIn(BaseModel):
    exercise: str
    replacement: str


@app.post("/sessions/{sid}/swap")
def swap_exercise(sid: int, s: SwapIn):
    """Replace an exercise in a live workout (before any set of it is logged), with a weight from your history."""
    with db() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404, "session not found")
        if row["finished_at"]:
            raise HTTPException(409, "session already finished")
        cur = con.execute("SELECT * FROM session_exercises WHERE session_id=? AND exercise=?", (sid, s.exercise)).fetchone()
        if not cur:
            raise HTTPException(404, "exercise not in this session")
        if con.execute("SELECT 1 FROM session_exercises WHERE session_id=? AND exercise=?", (sid, s.replacement)).fetchone():
            raise HTTPException(409, "replacement is already in this session")
        if con.execute("SELECT 1 FROM session_sets WHERE session_id=? AND exercise=?", (sid, s.exercise)).fetchone():
            raise HTTPException(409, "sets already logged for this exercise")
        if not library.describe(s.replacement)["primary"] and s.replacement not in {r["exercise"] for r in con.execute(
                "SELECT DISTINCT exercise FROM session_sets")}:
            raise HTTPException(422, "unknown exercise")
        match = next((c for c in build_pool(con, datetime.now(timezone.utc)) if c["exercise"] == s.replacement), None)
        weight = 0.0
        if match and match["e1rm"] and match["equipment"] != {"bodyweight"}:
            weight = generator.weight_for(match["e1rm"], cur["reps"], match["days_since"])
        con.execute("UPDATE session_exercises SET exercise=?, weight_kg=? WHERE id=?", (s.replacement, weight, cur["id"]))
        return session_out(con, row)


class HealthIn(BaseModel):
    avg_heart_rate: float | None = Field(default=None, ge=20, le=260)
    max_heart_rate: float | None = Field(default=None, ge=20, le=260)
    active_calories: float | None = Field(default=None, ge=0, le=10000)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    healthkit_uuid: str | None = None


@app.post("/sessions/{sid}/health")
def save_health(sid: int, h: HealthIn):
    """Attach the Apple Health summary (from the Watch) to a workout. Only the fields you send are changed."""
    fields = h.model_dump(exclude_none=True)
    with db() as con:
        if not con.execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone():
            raise HTTPException(404, "session not found")
        if fields:
            con.execute(f"UPDATE sessions SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), sid))
        return session_out(con, con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone())


# ---------- exercise info, videos ----------
def media_row(con, name):
    return con.execute("SELECT * FROM exercise_media WHERE exercise=?", (name,)).fetchone()


@app.get("/exercises/{name:path}/info")
def exercise_info(name: str):
    """Everything to remind you how to do an exercise: muscles, written form cues, your video and YouTube links."""
    meta = library.describe(name)
    with db() as con:
        m = media_row(con, name)
    video = media.signed_path(os.environ["API_TOKEN"], m["video_file"]) if m and m["video_file"] else None
    return {"exercise": name, "primary": meta["primary"], "secondary": meta["secondary"],
            "equipment": sorted(meta["equipment"])[0], "compound": meta["compound"], "cues": cues.cue_list(name),
            "video_url": video, "youtube": json.loads(m["youtube"]) if m else []}


class YouTubeLink(BaseModel):
    title: str
    url: str = Field(pattern=r"^https://(www\.)?youtube\.com/watch\?v=[\w-]+$|^https://youtu\.be/[\w-]+$")
    channel: str = ""
    views: int = 0


class MediaIn(BaseModel):
    youtube: list[YouTubeLink]


@app.put("/exercises/{name:path}/links")
def set_youtube_links(name: str, m: MediaIn):
    with db() as con:
        con.execute("INSERT INTO exercise_media (exercise, youtube) VALUES (?,?) "
                    "ON CONFLICT(exercise) DO UPDATE SET youtube=excluded.youtube",
                    (name, json.dumps([x.model_dump() for x in m.youtube])))
    return exercise_info(name)


@app.post("/exercises/{name:path}/video")
async def upload_video(name: str, request: Request):
    """Upload an mp4 clip (raw request body, Content-Type: video/mp4, up to 30 MB)."""
    if request.headers.get("content-type", "").split(";")[0] != "video/mp4":
        raise HTTPException(415, "send the clip as video/mp4")
    body = await request.body()
    if not body or len(body) > media.MAX_VIDEO_BYTES:
        raise HTTPException(413, f"clip must be 1 byte to {media.MAX_VIDEO_BYTES // 2**20} MB")
    filename = media.slug(name) + ".mp4"
    os.makedirs(MEDIA_DIR, exist_ok=True)
    with open(os.path.join(MEDIA_DIR, filename), "wb") as f:
        f.write(body)
    with db() as con:
        con.execute("INSERT INTO exercise_media (exercise, video_file) VALUES (?,?) "
                    "ON CONFLICT(exercise) DO UPDATE SET video_file=excluded.video_file", (name, filename))
    return exercise_info(name)


@app.get("/media/{filename}")
def get_media(filename: str, exp: int = 0, sig: str = ""):
    if not media.valid(os.environ.get("API_TOKEN", ""), filename, exp, sig):
        raise HTTPException(403, "link expired or invalid")
    try:
        with open(os.path.join(MEDIA_DIR, filename), "rb") as f:
            return Response(f.read(), media_type="video/mp4", headers={"Cache-Control": "private, max-age=3600"})
    except FileNotFoundError:
        raise HTTPException(404, "no such clip")


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
