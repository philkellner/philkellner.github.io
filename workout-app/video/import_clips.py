"""Upload your generated clips (and the YouTube links, if you ran find_videos.py) to the workout server.

    export SERVER_URL=https://your-server  API_TOKEN=...
    python import_clips.py clips/            # clips named like prompts.md says, e.g. clips/back-squat.mp4

Clips are shrunk with ffmpeg first when it is installed (720p, no audio, H.264), which keeps them to a few MB.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server"))
from media import slug  # noqa: E402


def match_clips(clips_dir, exercises):
    """Pair each .mp4 in the folder with an exercise by file name. Returns (matched {exercise: path}, unmatched [files])."""
    by_slug = {slug(e): e for e in exercises}
    matched, unmatched = {}, []
    for f in sorted(os.listdir(clips_dir)):
        if not f.lower().endswith(".mp4"):
            continue
        name = by_slug.get(slug(os.path.splitext(f)[0]))
        if name:
            matched[name] = os.path.join(clips_dir, f)
        else:
            unmatched.append(f)
    return matched, unmatched


def shrink(path):
    """A small web-friendly copy of the clip, or the original if ffmpeg isn't available or fails."""
    if not shutil.which("ffmpeg"):
        return path
    out = os.path.join(tempfile.mkdtemp(), "clip.mp4")
    r = subprocess.run(["ffmpeg", "-y", "-i", path, "-an", "-vf", "scale=-2:'min(720,ih)'", "-c:v", "libx264",
                        "-crf", "28", "-preset", "veryfast", "-movflags", "+faststart", out], capture_output=True)
    return out if r.returncode == 0 else path


def call(method, url, token, data=None, content_type="application/json"):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def main(clips_dir):
    server, token = os.environ.get("SERVER_URL"), os.environ.get("API_TOKEN")
    if not server or not token:
        sys.exit("Set SERVER_URL and API_TOKEN first.")
    index = [r["exercise"] for r in json.load(open(os.path.join(HERE, "exercise_index.json")))]
    matched, unmatched = match_clips(clips_dir, index)
    for ex, path in matched.items():
        data = open(shrink(path), "rb").read()
        call("POST", f"{server}/exercises/{urllib.parse.quote(ex)}/video", token, data, "video/mp4")
        print(f"uploaded {ex} ({len(data) / 1e6:.1f} MB)")
    links_path = os.path.join(HERE, "youtube_videos.json")
    if os.path.exists(links_path):
        for ex, vids in json.load(open(links_path)).items():
            body = {"youtube": [{k: v[k] for k in ("title", "url", "channel", "views")} for v in vids]}
            call("PUT", f"{server}/exercises/{urllib.parse.quote(ex)}/links", token, json.dumps(body).encode())
        print("linked YouTube videos")
    if unmatched:
        print("no exercise matched these files (rename them to an exercise name):", ", ".join(unmatched))


if __name__ == "__main__":
    main(sys.argv[1])
