# Workout app

- `server/`: FastAPI + SQLite API. Templates, sessions, logged sets. Used by the iPhone app, Watch app and Discord coach.
- `ios/`: SwiftUI iPhone app + watchOS app (XcodeGen project).

## Server
```
cd server && pip install -r requirements.txt
export API_TOKEN=$(openssl rand -hex 24)      # keep this; the apps and bot send it as a Bearer token
python seed.py ../../workout-coach/profile.json   # loads Chest & Triceps / Back & Biceps / Shoulders / Legs
uvicorn app:app --host 0.0.0.0 --port 8000
pytest                                          # 4 tests
```
Deploy it anywhere with HTTPS (Fly.io, Railway, a VPS behind Caddy). Set `DB_PATH` to a persistent volume.

## iPhone + Watch (on your Mac)
```
brew install xcodegen
cd ios && edit project.yml (bundle IDs, DEVELOPMENT_TEAM) && xcodegen && open Workout.xcodeproj
```
Run the **Workout** scheme on your iPhone, tap **Server**, enter the URL and token. The phone pushes them to the Watch
via WatchConnectivity. On the Watch: tap a workout to start it, tap **Done** after each set, **Finish** at the end.
A workout started on the phone or through the API shows up as **Resume …** on the Watch (it refreshes on launch and
whenever the app becomes active).

## API
`GET/POST /templates`, `PUT/DELETE /templates/{id}`, `POST /sessions {template_id, source}`, `GET /sessions/active`,
`GET /sessions`, `POST /sessions/{id}/sets`, `POST /sessions/{id}/finish`. All need `Authorization: Bearer $API_TOKEN`.

## Status
Server is tested. The Swift code has **not been compiled** (written without Xcode); expect to fix small build errors on first build.
Not in v1: HealthKit/heart rate, rest timer, Watch-side editing of weights/reps.
