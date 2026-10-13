import os
import tempfile
import time
from urllib.parse import urlsplit

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "m.db"))
os.environ.setdefault("API_TOKEN", "secret")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402
import cues  # noqa: E402
import media  # noqa: E402

H = {"Authorization": "Bearer secret"}
MP4 = {**H, "Content-Type": "video/mp4"}
c = TestClient(app.app)


@pytest.fixture(autouse=True)
def media_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "MEDIA_DIR", str(tmp_path / "media"))


def test_info_has_written_cues_and_muscles():
    j = c.get("/exercises/Back Squat/info", headers=H).json()
    assert j["primary"] == ["quads"] and j["equipment"] == "barbell" and len(j["cues"]) >= 3
    assert j["video_url"] is None and j["youtube"] == []
    unknown = c.get("/exercises/Some Made Up Move/info", headers=H).json()
    assert unknown["cues"] == [] and unknown["primary"] == []


def test_cue_helpers():
    assert cues.cue_list("Plank")[0].startswith("forearms") and cues.cue_list("Nope") == []
    assert all(cues.cue_list(name) for name in cues.CUES)


def test_upload_serve_and_signature_rules():
    url = "/exercises/Back Squat/video"
    assert c.post(url, content=b"x", headers={"Content-Type": "video/mp4"}).status_code == 401
    assert c.post(url, content=b"x", headers={**H, "Content-Type": "image/png"}).status_code == 415
    assert c.post(url, content=b"", headers=MP4).status_code == 413
    info = c.post(url, content=b"FAKE-MP4-BYTES", headers=MP4).json()
    assert info["video_url"].startswith("/media/back-squat.mp4?exp=")

    got = c.get(info["video_url"])                      # no Authorization header needed
    assert got.status_code == 200 and got.content == b"FAKE-MP4-BYTES" and got.headers["content-type"] == "video/mp4"

    parts = urlsplit(info["video_url"])
    assert c.get(parts.path + parts.query.replace("sig=", "sig=0")).status_code == 403          # wrong signature
    assert c.get("/media/back-squat.mp4").status_code == 403                                     # unsigned
    past = int(time.time()) - 10
    assert c.get(f"/media/back-squat.mp4?exp={past}&sig={media.sign('secret', 'back-squat.mp4', past)}").status_code == 403
    future = int(time.time()) + 60
    assert c.get(f"/media/Bad_Name.mp4?exp={future}&sig={media.sign('secret', 'Bad_Name.mp4', future)}").status_code == 403
    assert c.get(f"/media/other.mp4?exp={future}&sig={media.sign('secret', 'other.mp4', future)}").status_code == 404   # signed but missing


def test_oversize_upload_rejected(monkeypatch):
    monkeypatch.setattr(media, "MAX_VIDEO_BYTES", 10)
    assert c.post("/exercises/Deadlift/video", content=b"x" * 11, headers=MP4).status_code == 413


def test_youtube_links_validated_and_replaced():
    good = {"title": "Squat tutorial", "url": "https://www.youtube.com/watch?v=abc_123-X", "channel": "C", "views": 5}
    assert c.put("/exercises/Back Squat/links", headers=H, json={"youtube": [good]}).json()["youtube"][0]["views"] == 5
    for bad in ["https://evil.example/watch?v=abc", "javascript:alert(1)", "https://youtube.com.evil.example/watch?v=abc"]:
        assert c.put("/exercises/Back Squat/links", headers=H, json={"youtube": [dict(good, url=bad)]}).status_code == 422
    assert c.put("/exercises/Back Squat/links", headers=H, json={"youtube": []}).json()["youtube"] == []


def test_links_and_video_do_not_overwrite_each_other():
    good = {"title": "T", "url": "https://youtu.be/abcdef", "channel": "", "views": 1}
    c.put("/exercises/Leg Press/links", headers=H, json={"youtube": [good]})
    j = c.post("/exercises/Leg Press/video", content=b"v", headers=MP4).json()
    assert j["video_url"] and len(j["youtube"]) == 1
    j = c.put("/exercises/Leg Press/links", headers=H, json={"youtube": []}).json()
    assert j["video_url"] and j["youtube"] == []
