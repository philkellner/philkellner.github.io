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
pytest                                          # 45 tests
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
Progression: when you start a workout, each exercise's weight/reps come from your history (hit all target reps: add weight;
miss: repeat; miss twice: deload ~10%; 4+ weeks off: restart at 90%, 8+ weeks at 80%), with the reason shown. A brand-new
exercise keeps the template's numbers; `GET /exercises/{name}/suggestion` shows the current suggestion.
Recovery: `GET /recovery` (per-muscle %) and `GET /recommendation` (templates ranked by readiness) use `muscles.py`
(exercise to muscle map) and `recovery.py` (fatigue model); both take `?as_of=<ISO time>` to look ahead.
Generator: `POST /generate {minutes, goal: strength|hypertrophy|endurance, profile, template | muscles, variety 0..1, exclude, seed}`
returns a draft (nothing saved); `POST /sessions/custom` starts it. With no `template`/`muscles` it picks your most recovered
day and drops muscles that are still sore. Exercises come from your history (done 2+ times) plus a small built-in library,
filtered by an equipment profile. `POST /equipment-profiles/derive` builds "From my history" and "Recent training" from what
you've logged (`import_history.py` does this for you); the former is the default. Weights are your last estimated 1RM at ~2 reps
in reserve (80-90% after a layoff); new exercises start at 0 with a note to find a light weight.
Swaps: `GET /exercises/{name}/alternatives`, `POST /sessions/{id}/swap` (only before sets are logged for that exercise).

## Exercise videos and form tips
Each exercise has an info screen (the (i) button in a workout, or Progress > exercise > How to do it): written form steps first,
your looping reminder clip if you have one, muscles worked and popular YouTube tutorials. The Watch shows the written steps
under "Form tips". Server: `GET /exercises/{name}/info`, `POST /exercises/{name}/video` (mp4, 30 MB), `PUT .../links`;
clips are served through signed, expiring links (`MEDIA_DIR` should be on a persistent volume). Cues live in `server/cues.py`
(40 exercises so far). Making the clips: see `video/README.md`.

## Apple Health
- **Watch:** starting or resuming a workout on the Watch starts an Apple Health strength-training session
  (`ios/Watch/WorkoutRecorder.swift`): live heart rate and active calories on the workout screen, the app keeps running
  between sets, and the workout is saved to Health when you tap Finish or End workout. Avg/max heart rate, calories and
  duration are also sent to the server (`POST /sessions/{id}/health`) and shown in History.
- **Phone-only workouts:** finishing on the iPhone saves a workout (no heart rate) to Health, unless the Watch recorded it.
  Finish on the device you started on; finishing on the phone while the Watch is recording would save two workouts.
- **Setup:** `project.yml` already adds the HealthKit entitlement, usage strings and the Watch `workout-processing` background
  mode. If Xcode complains about the HealthKit capability, open each target's *Signing & Capabilities* and add it once.
  On first use the Watch asks for Health permission (approve it on the iPhone's Health prompt if shown).
- **Testing:** the Watch simulator produces no heart rate, so test on a real Watch. If you deny Health access the
  workout still works, just without heart rate.
- Not recorded: individual sets are not written to Health (it has no strength-set type), only the workout as a whole.
Units: server stores kg; phone Settings switches display between lb and kg (default lb) and syncs to the Watch.
