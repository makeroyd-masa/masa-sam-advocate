"""Download pilot.db on first boot (for hosts without volume file upload, e.g. Railway).

Streams PILOT_DB_URL to PILOT_DB_PATH. No-op if the file already exists (the volume
persists across restarts, so this runs only on the first deploy). Uses only the
stdlib (the slim image has no curl). Supports an optional bearer token for private
sources (e.g. a GitHub Release asset), dropping it on cross-host redirects so the
signed storage URL isn't rejected.

Env:
  PILOT_DB_URL     required — direct/redirecting download URL
  PILOT_DB_PATH    destination (default /data/pilot.db)
  PILOT_DB_BEARER  optional — Authorization: Bearer <token> for the first hop
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
from urllib.parse import urlparse


class _StripAuthOnCrossHost(urllib.request.HTTPRedirectHandler):
    """GitHub asset URLs 302 to a signed storage host that rejects the GitHub
    token; drop Authorization when the redirect leaves the original host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urlparse(newurl).netloc != urlparse(req.full_url).netloc:
            new.headers = {k: v for k, v in new.headers.items() if k.lower() != "authorization"}
        return new


def main() -> int:
    url = os.environ.get("PILOT_DB_URL")
    dest = os.environ.get("PILOT_DB_PATH", "/data/pilot.db")
    if not url:
        print("PILOT_DB_URL not set — skipping pilot.db fetch.")
        return 0
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"pilot.db already present at {dest} — skipping fetch.")
        return 0

    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    req = urllib.request.Request(url)
    bearer = os.environ.get("PILOT_DB_BEARER")
    if bearer:
        req.add_header("Authorization", f"Bearer {bearer}")
        req.add_header("Accept", "application/octet-stream")

    opener = urllib.request.build_opener(_StripAuthOnCrossHost)
    print(f"Fetching pilot.db from {urlparse(url).netloc} -> {dest} ...")
    tmp = dest + ".part"
    with opener.open(req) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out, length=1024 * 1024)
    os.replace(tmp, dest)
    print(f"pilot.db downloaded: {os.path.getsize(dest):,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
