"""Find the most-viewed YouTube demos for each exercise in exercise_index.json.

Needs a YouTube Data API v3 key: https://console.cloud.google.com/ -> enable "YouTube Data API v3" -> Credentials.
    export YOUTUBE_API_KEY=...
    python find_videos.py --limit 40 --top 3

Quota: the free allowance is 10,000 units/day and each exercise costs ~101 (one search + one stats lookup), so ~95
exercises per day. Results are cached in youtube_videos.json; re-run the next day to continue where it stopped.
These are links for you to watch (or open from the app); the script never downloads video.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://www.googleapis.com/youtube/v3"
HERE = os.path.dirname(os.path.abspath(__file__))
MIN_SECONDS, MAX_SECONDS = 20, 480       # skip Shorts-length clips and long vlogs/programs
GENERIC = {"exercise", "proper", "form", "how", "to", "the", "a", "with", "and"}


class QuotaExceeded(Exception):
    pass


def http_get(path, params):
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if e.code == 403 and "quota" in body.lower():
            raise QuotaExceeded(body)
        raise


def parse_duration(iso):
    m = re.fullmatch(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def relevant(title, exercise):
    """Most of the exercise's words must appear in the title (so 'Bench Press' doesn't return a random vlog)."""
    words = [w for w in re.findall(r"[a-z]+", exercise.lower()) if w not in GENERIC]
    t = title.lower()
    return bool(words) and sum(w in t for w in words) >= max(1, round(len(words) * 0.7))


def pick(videos, exercise, top):
    ok = [v for v in videos if MIN_SECONDS <= v["duration_s"] <= MAX_SECONDS and relevant(v["title"], exercise)]
    return sorted(ok, key=lambda v: -v["views"])[:top]


def search(exercise, query, key, top=3, fetch=http_get):
    found = fetch("search", {"part": "snippet", "q": query, "type": "video", "order": "viewCount", "maxResults": 25,
                             "relevanceLanguage": "en", "safeSearch": "strict", "key": key})
    ids = [i["id"]["videoId"] for i in found.get("items", []) if i.get("id", {}).get("videoId")]
    if not ids:
        return []
    stats = fetch("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids), "key": key})
    videos = [{"id": v["id"], "url": f"https://www.youtube.com/watch?v={v['id']}", "title": v["snippet"]["title"],
               "channel": v["snippet"]["channelTitle"], "published": v["snippet"]["publishedAt"][:10],
               "views": int(v.get("statistics", {}).get("viewCount", 0)),
               "duration_s": parse_duration(v["contentDetails"]["duration"])} for v in stats.get("items", [])]
    return pick(videos, exercise, top)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=os.path.join(HERE, "exercise_index.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "youtube_videos.json"))
    ap.add_argument("--limit", type=int, default=40, help="only the N most-used exercises")
    ap.add_argument("--top", type=int, default=3)
    args = ap.parse_args()
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        sys.exit("Set YOUTUBE_API_KEY first (see the top of this file).")
    index = [r for r in json.load(open(args.index)) if r["kind"] == "strength"][:args.limit]
    results = json.load(open(args.out)) if os.path.exists(args.out) else {}
    try:
        for r in index:
            if r["exercise"] in results:
                continue
            results[r["exercise"]] = search(r["exercise"], r["youtube_query"], key, args.top)
            print(f"{r['priority']:3d} {r['exercise']:34s} {len(results[r['exercise']])} videos")
    except QuotaExceeded:
        print("Daily YouTube quota used up; run again tomorrow to continue.")
    finally:
        json.dump(results, open(args.out, "w"), indent=1)
        print(f"saved {len(results)} exercises to {args.out}")


if __name__ == "__main__":
    main()
