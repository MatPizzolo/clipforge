"""Regression tests for the final-review findings (at-least-once delivery, crashes)."""

from datetime import timedelta

from clipforge.models import JobStatus, StageName
from clipforge.pipeline.steps import Step, dispatch, fail_job, sanitize, sweep
from tests.pipeline.harness import Harness


def _steps(h: Harness, step: Step) -> int:
    return [c.step for c in h.spawner.spawned].count(step)


# ---- #1: failing a job must not depend on winning the claim


def test_fail_job_writes_failed_even_if_the_claim_was_already_taken(harness: Harness) -> None:
    job_id = harness.submit()
    harness.spawner.queue.clear()
    harness.store.claim(job_id, "failed")  # a previous fail_job crashed right after its claim
    fail_job(harness.deps, job_id, StageName.INGEST, "permanent", "not a direct media link")
    assert harness.store.get(job_id).status is JobStatus.FAILED


def test_sweeper_fails_a_stalled_job_whose_failed_claim_is_held(harness: Harness) -> None:
    job_id = harness.submit()
    harness.spawner.queue.clear()
    harness.store.claim(job_id, "failed")
    start = harness.store.get(job_id).updated_at
    sweep(harness.deps, now=start + timedelta(hours=1))
    assert harness.store.get(job_id).status is JobStatus.FAILED


# ---- #2: late and duplicate steps must be no-ops once their output is recorded


def test_late_duplicate_step_does_not_rerun_or_respawn(harness: Harness) -> None:
    job_id = harness.submit()
    harness.run_until(Step.CLIP)  # transcribe and highlights are recorded
    calls_before = harness.stages.calls["transcribe"]
    queued_before = len(harness.spawner.queue)
    dispatch(harness.deps, Step.TRANSCRIBE, job_id)  # a late redelivery
    assert harness.stages.calls["transcribe"] == calls_before
    assert len(harness.spawner.queue) == queued_before
    assert harness.store.get(job_id).stage is StageName.RENDER


def test_late_duplicate_cannot_fail_a_progressing_job(harness: Harness) -> None:
    job_id = harness.submit()
    harness.run_until(Step.CLIP)
    for _ in range(3):
        harness.store.incr_attempts(job_id, Step.TRANSCRIBE)  # attempts already used up
    harness.stages.transient["transcribe"] = 1
    dispatch(harness.deps, Step.TRANSCRIBE, job_id)
    harness.run()
    assert harness.store.get(job_id).status is JobStatus.DONE


def test_duplicate_ingest_does_not_amplify_downstream(harness: Harness) -> None:
    job_id = harness.submit()
    harness.spawner.spawn(Step.INGEST, job_id)
    harness.run()
    assert _steps(harness, Step.TRANSCRIBE) == 1
    assert _steps(harness, Step.HIGHLIGHTS) == 1
    assert _steps(harness, Step.CLIP) == 5
    assert harness.stages.calls["transcribe"] == 1


def test_a_failed_spawn_is_retried_not_lost(harness: Harness) -> None:
    real_spawn = harness.spawner.spawn
    failed_once = False

    def flaky_spawn(step: str, job_id: str, clip_id: str | None = None) -> None:
        nonlocal failed_once
        if step == Step.TRANSCRIBE and not failed_once:
            failed_once = True
            raise RuntimeError("modal API hiccup")
        real_spawn(step, job_id, clip_id)

    harness.spawner.spawn = flaky_spawn  # type: ignore[method-assign]
    job_id = harness.submit()
    harness.run()
    assert harness.store.get(job_id).status is JobStatus.DONE
    assert _steps(harness, Step.TRANSCRIBE) == 1


# ---- #3: a crash between marking done and notifying must not lose the message


def _crash_first_call(h: Harness, event: str) -> None:
    real = h.deps.notifier
    crashed = False

    def notifier(job):  # type: ignore[no-untyped-def]
        inner = real(job)
        original = getattr(inner, event)

        def once(*args):  # type: ignore[no-untyped-def]
            nonlocal crashed
            if not crashed:
                crashed = True
                raise RuntimeError("container died")  # SafeNotifier is bypassed here on purpose
            return original(*args)

        setattr(inner, event, once)
        return inner

    h.deps.notifier = notifier  # type: ignore[method-assign]


def test_clip_video_is_sent_after_a_crash_before_notify(harness: Harness) -> None:
    _crash_first_call(harness, "clip_ready")
    job_id = harness.submit()
    harness.run()
    assert harness.store.get(job_id).status is JobStatus.DONE
    assert harness.event_kinds().count("clip_ready") == 5


def test_done_message_is_sent_after_a_crash_before_notify(harness: Harness) -> None:
    _crash_first_call(harness, "done")
    job_id = harness.submit()
    harness.run()
    assert harness.store.get(job_id).status is JobStatus.DONE
    assert harness.event_kinds().count("done") == 1


def test_a_broken_notifier_factory_does_not_fail_the_job(harness: Harness) -> None:
    def factory(job):  # type: ignore[no-untyped-def]
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")

    harness.deps.notifier_for = factory
    job_id = harness.submit()
    harness.run()
    assert harness.store.get(job_id).status is JobStatus.DONE
    assert harness.retries_seen == 0  # a notifier problem must never burn step attempts


# ---- #4: secrets outside the query string


def test_sanitize_redacts_bot_tokens_and_userinfo() -> None:
    url = "https://api.telegram.org/file/bot123456:AAH-x_9QzA/videos/f.mp4"
    assert "AAH-x_9QzA" not in sanitize(f"Client error '404' for url '{url}'")
    assert "bot<redacted>" in sanitize(url)
    leaked = sanitize("failed https://user:hunter2@cdn.example.com/v.mp4")
    assert "hunter2" not in leaked and "cdn.example.com/v.mp4" in leaked
