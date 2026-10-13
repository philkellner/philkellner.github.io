# Workout app

- `server/`: FastAPI + SQLite API. Templates, sessions, logged sets. Used by the iPhone app, Watch app and Discord coach.
- `ios/`: SwiftUI iPhone app + watchOS app (XcodeGen project).

## Server
```
cd server && pip install -r requirements.txt
export API_TOKEN=$(openssl rand -hex 24)      # keep this; the apps and bot send it as a Bearer token
python seed.py ../../workout-coach/profile.json   # loads Chest & Triceps / Back & Biceps / Shoulders / Legs
python import_history.py ~/Downloads/WorkoutExport.csv   # optional: your past workouts (safe to re-run)
uvicorn app:app --host 0.0.0.0 --port 8000
pytest                                          # 9 tests
```
Deploy it anywhere with HTTPS (Fly.io, Railway, a VPS behind Caddy). Set `DB_PATH` to a persistent volume.

## iPhone + Watch (on your Mac)
```
brew install xcodegen
cd ios && edit project.yml (bundle IDs, DEVELOPMENT_TEAM) && xcodegen && open Workout.xcodeproj
```
Run the **Workout** scheme on your iPhone, tap **Server**, enter the URL and token. The phone pushes them to the Watch
via WatchConnectivity. On the Watch: tap a workout to start it, set reps (+/-) and weight (Digital Crown), tap **Log set**, rest while the timer counts down (a tap on the wrist when it ends), **Finish** at the end. Each set is prefilled from what you did last time.
A workout started on the phone or through the API shows up as **Resume …** on the Watch (it refreshes on launch and
whenever the app becomes active).

## API
`GET/POST /templates`, `PUT/DELETE /templates/{id}`, `POST /sessions {template_id, source}`, `GET /sessions/active`,
`GET /sessions`, `POST /sessions/{id}/sets {exercise,set_index,reps,weight_kg,is_warmup}`, `PATCH/DELETE /sessions/{id}/sets/{set_id}`, `POST /sessions/{id}/finish`, `GET /exercises`, `GET /exercises/{name}/history`. All need `Authorization: Bearer $API_TOKEN`.

## Status
Server is tested. The Swift code has **not been compiled** (written without Xcode); expect to fix small build errors on first build.
Not yet: HealthKit/heart rate, progressive-overload suggestions, recovery tracking, workout generation, swaps.
Units: server stores kg; phone Settings switches display between lb and kg (default lb) and syncs to the Watch.
