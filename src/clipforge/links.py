"""Signed, expiring download links for job zips (ADR-13).

`sig = HMAC-SHA256(DOWNLOAD_SIGNING_KEY, f"{job_id}:{exp}")`. The link carries only the job id,
the expiry and the signature; the key never leaves the server.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from clipforge.config import Settings
from clipforge.models import JobStatus, JobView


class LinksNotConfigured(RuntimeError):
    """API_URL or DOWNLOAD_SIGNING_KEY is missing, so no link can be made."""


def sign(key: str, job_id: str, exp: int) -> str:
    return hmac.new(key.encode(), f"{job_id}:{exp}".encode(), hashlib.sha256).hexdigest()


def verify(key: str, job_id: str, exp: int, sig: str, now: float | None = None) -> bool:
    if exp <= (time.time() if now is None else now):
        return False
    return hmac.compare_digest(sign(key, job_id, exp), sig)


def download_url(settings: Settings, job_id: str, now: float | None = None) -> str:
    if settings.api_url is None or settings.download_signing_key is None:
        raise LinksNotConfigured("set API_URL and DOWNLOAD_SIGNING_KEY to make download links")
    exp = int(time.time() if now is None else now) + settings.download_link_ttl_s
    sig = sign(settings.download_signing_key.get_secret_value(), job_id, exp)
    return f"{settings.api_url.rstrip('/')}/jobs/{job_id}/download?exp={exp}&sig={sig}"


def with_download_url(view: JobView, settings: Settings, now: float | None = None) -> JobView:
    """The view with a fresh signed link when the job is done and links are configured."""
    if view.status is not JobStatus.DONE or view.output_zip is None:
        return view
    try:
        url = download_url(settings, view.job_id, now)
    except LinksNotConfigured:
        return view
    return view.model_copy(update={"download_url": url})
