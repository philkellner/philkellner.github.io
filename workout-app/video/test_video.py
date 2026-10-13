import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import find_videos as fv  # noqa: E402
import make_prompts as mp  # noqa: E402


def video(id, title, views, dur="PT2M10S"):
    return {"id": id, "snippet": {"title": title, "channelTitle": "Chan", "publishedAt": "2020-01-02T00:00:00Z"},
            "statistics": {"viewCount": str(views)}, "contentDetails": {"duration": dur}}


def fake_fetch(path, params):
    if path == "search":
        return {"items": [{"id": {"videoId": v}} for v in ["a", "b", "c", "d", "e"]]}
    return {"items": [video("a", "How To Bench Press Properly", 5_000_000),
                      video("b", "My gym vlog", 90_000_000),                       # popular but irrelevant
                      video("c", "Bench Press form tips", 2_000_000, "PT45S"),
                      video("d", "Barbell Bench Press Tutorial", 3_000_000, "PT1H5M"),   # too long
                      video("e", "Barbell Bench Press for beginners", 4_000_000, "PT6M")]}


def test_duration_and_relevance():
    assert fv.parse_duration("PT1H2M3S") == 3723 and fv.parse_duration("PT45S") == 45 and fv.parse_duration("P0D") == 0
    assert fv.relevant("Barbell Bench Press tutorial", "Barbell Bench Press") and not fv.relevant("Squat day", "Barbell Bench Press")


def test_picks_most_viewed_relevant_clips_of_sane_length():
    got = fv.search("Barbell Bench Press", "q", "KEY", top=3, fetch=fake_fetch)
    assert [v["id"] for v in got] == ["a", "e", "c"]
    assert got[0]["views"] == 5_000_000 and got[0]["url"].endswith("watch?v=a")
    assert "b" not in [v["id"] for v in got] and "d" not in [v["id"] for v in got]


def test_no_search_results():
    assert fv.search("X", "q", "K", fetch=lambda p, q: {"items": []}) == []


def test_every_cue_has_an_index_exercise_and_prompts_are_complete():
    idx = json.load(open(os.path.join(os.path.dirname(__file__), "exercise_index.json")))
    names = {r["exercise"] for r in idx}
    from cues import CUES
    assert set(CUES) <= names
    row = next(r for r in idx if r["exercise"] == "Back Squat")
    p = mp.prompt_for(row)
    assert "Back Squat" in p and "barbell" in p and "exactly 3 reps" in p
