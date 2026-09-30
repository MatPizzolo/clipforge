"""Signed, expiring zip links (ADR-13)."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from clipforge.config import Settings
from clipforge.links import LinksNotConfigured, download_url, sign, verify, with_download_url
from clipforge.models import CostSummary, JobStatus, JobView, StageName

JOB = "20260923-aaaaaaaa-0001"
NOW = 1_800_000_000.0


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "api_url": "https://api.example/",
        "download_signing_key": "k3y",
        "download_link_ttl_s": 3600,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def _view(status: JobStatus, output_zip: str | None) -> JobView:
    at = datetime(2026, 9, 23, tzinfo=UTC)
    return JobView(
        job_id=JOB,
        status=status,
        stage=StageName.PACKAGE,
        clips=[],
        cost=CostSummary(),
        created_at=at,
        updated_at=at,
        output_zip=output_zip,
    )


def test_sign_verify_round_trip() -> None:
    sig = sign("k3y", JOB, 1_800_000_100)
    assert len(sig) == 64 and "k3y" not in sig
    assert verify("k3y", JOB, 1_800_000_100, sig, now=NOW)


def test_verify_rejects_expired_tampered_and_other_job() -> None:
    exp = 1_800_000_100
    sig = sign("k3y", JOB, exp)
    assert not verify("k3y", JOB, exp, sig, now=exp)  # expiry is exclusive
    assert not verify("k3y", JOB, exp + 1, sig, now=NOW)  # exp changed
    assert not verify("k3y", JOB, exp, sig[:-1] + "0", now=NOW)
    assert not verify("k3y", "20260923-bbbbbbbb-0001", exp, sig, now=NOW)
    assert not verify("other", JOB, exp, sig, now=NOW)


def test_download_url_is_signed_and_expires_after_ttl() -> None:
    url = download_url(_settings(), JOB, now=NOW)
    parts = urlsplit(url)
    assert (
        f"{parts.scheme}://{parts.netloc}{parts.path}" == f"https://api.example/jobs/{JOB}/download"
    )
    query = parse_qs(parts.query)
    exp = int(query["exp"][0])
    assert exp == int(NOW) + 3600
    assert verify("k3y", JOB, exp, query["sig"][0], now=NOW)


@pytest.mark.parametrize("missing", ["api_url", "download_signing_key"])
def test_download_url_needs_config(missing: str) -> None:
    with pytest.raises(LinksNotConfigured):
        download_url(_settings(**{missing: None}), JOB, now=NOW)


def test_with_download_url_only_for_done_jobs_with_a_zip() -> None:
    settings = _settings()
    done = with_download_url(_view(JobStatus.DONE, f"{JOB}/job.zip"), settings, now=NOW)
    assert done.download_url is not None and done.download_url.startswith("https://api.example/")
    running = with_download_url(_view(JobStatus.RUNNING, None), settings, now=NOW)
    assert running.download_url is None
    unconfigured = _settings(download_signing_key=None)
    assert with_download_url(_view(JobStatus.DONE, "x"), unconfigured).download_url is None
