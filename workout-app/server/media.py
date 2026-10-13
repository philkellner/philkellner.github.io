"""Exercise videos: signed, expiring URLs for files in MEDIA_DIR (so a video can be fetched without sending your API token)."""
import hashlib
import hmac
import re
import time

URL_TTL_SECONDS = 6 * 3600
MAX_VIDEO_BYTES = 30 * 1024 * 1024


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def sign(secret, filename, expires):
    return hmac.new(secret.encode(), f"{filename}|{expires}".encode(), hashlib.sha256).hexdigest()


def signed_path(secret, filename, now=None):
    expires = int((now if now is not None else time.time()) + URL_TTL_SECONDS)
    return f"/media/{filename}?exp={expires}&sig={sign(secret, filename, expires)}"


def valid(secret, filename, exp, sig, now=None):
    if not re.fullmatch(r"[a-z0-9-]+\.mp4", filename):
        return False
    if exp < (now if now is not None else time.time()):
        return False
    return hmac.compare_digest(sign(secret, filename, exp), sig)
