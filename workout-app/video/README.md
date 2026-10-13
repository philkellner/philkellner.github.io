# Exercise videos

1. `python build_index.py WorkoutExport.csv` -> `exercise_index.{json,csv,md}`: every exercise you've logged, ranked by use,
   with muscles and equipment. The top 25 cover ~74% of your sessions and the top 40 ~86%, so start there.
2. `YOUTUBE_API_KEY=... python find_videos.py --limit 40` -> `youtube_videos.json`: the 3 most-viewed relevant demos per
   exercise (20 s to 8 min, title must match the exercise). Needs a free YouTube Data API key; ~95 exercises per day of quota.
   View count means popular, not necessarily good technique: skim before you trust one.
3. `python make_prompts.py` -> `prompts.md`: ready-to-paste text-to-video prompts with form cues for your top lifts
   (cues live in `cues.py`; read them over, they are general technique, not individual advice).

## Using the YouTube videos
Link to them or open them from the app. Do not download or re-upload them, and do not feed them to a video model:
that breaks YouTube's terms and the creators' copyright. Watching them to check your own cues is fine.

## The plan: AI clips as reminders, written steps as the source of truth
The clips only need to jog your memory. The app shows the written form steps (`server/cues.py`) above every clip, labelled
as an AI reminder, so a clip that gets a detail wrong does no harm. Workflow:
1. `python make_prompts.py` -> `prompts.md` (one prompt per exercise, with the file name to save the clip as).
2. Paste each prompt into the video generator you choose, 5-10 s each, and save the clip as `clips/<name>.mp4`.
3. `SERVER_URL=... API_TOKEN=... python import_clips.py clips/` shrinks (if ffmpeg is installed) and uploads them, and links the YouTube videos too.
Skim each clip once and delete any that show something clearly unsafe (e.g. a rounded back on a deadlift); that exercise just
falls back to its written steps.

## Other ways to make your own videos
Realistic options, best accuracy first:
1. **Film yourself** (phone on a tripod, ~20 s per exercise, ~40 exercises). Always correct, and it is your gym and your lifts.
2. **Keyframes + AI**: photograph yourself at the start and end position, then let an image-to-video model fill the motion
   (several current models accept first/last frames). Better than pure text because the key poses are real.
3. **Text-to-video from `prompts.md`**: fastest to try, least reliable. Models often get barbell paths, grips, joint angles,
   rep counts and the number of plates wrong, and a clip that looks plausible but shows bad form is worse than no clip.
Whatever you use, check each clip against its cues before publishing it, and mark `"reviewed": true` in `prompts.json`.
