"""The Modal app definition imports and wires up without contacting Modal."""

import re
from pathlib import Path

import clipforge
from clipforge import app


def test_app_definition() -> None:
    assert app.app.name == "clipforge"
    assert app.GPU == "L4"
    assert hasattr(app, "gpu_doctor")
    assert hasattr(app, "doctor")


def test_whisper_model_matches_settings() -> None:
    from clipforge.config import Settings

    assert Settings(_env_file=None).whisper_model == app.WHISPER_MODEL


def test_whisper_image_pins_its_gpu_packages() -> None:
    # faster-whisper 1.2.1 breaks on PyAV 18+; uv.lock changes must never float av in this image
    pins = dict(p.split("==") for p in app.WHISPER_PINS)
    assert pins == {"faster-whisper": "1.2.1", "ctranslate2": "4.8.2", "av": "17.0.0"}


def test_step_functions_and_endpoints_exist() -> None:
    for name in (
        "ingest_step",
        "transcribe_step",
        "highlights_step",
        "clip_step",
        "package_step",
        "sweeper",
        "dispatcher",
        "dispatch_task",
        "posting_daily",
        "db_doctor",
        "web",
        "smoke",
        "doctor",
    ):
        assert hasattr(app, name), name


def test_spawner_covers_every_step() -> None:
    # FunctionSpawner raises ValueError if a step has no function; building needs no Modal call.
    assert app._spawner() is not None


def test_container_env_points_at_the_image_dirs() -> None:
    assert app.CONTAINER_ENV["JOBS_ROOT"] == "/jobs"
    assert app.CONTAINER_ENV["PROMPTS_DIR"] == app.PROMPTS_MOUNT
    assert app.CONTAINER_ENV["FONTS_DIR"] == app.FONTS_MOUNT
    assert (app.REPO_ROOT / "prompts" / "metadata.json").is_file()
    assert (app.REPO_ROOT / "assets" / "fonts" / "Anton-Regular.ttf").is_file()


def test_only_app_imports_modal() -> None:
    src = Path(clipforge.__file__).parent
    pattern = re.compile(r"^\s*(import modal|from modal)", re.MULTILINE)
    offenders = [
        str(path.relative_to(src))
        for path in src.rglob("*.py")
        if path.name != "app.py" and pattern.search(path.read_text())
    ]
    assert offenders == []


def test_repo_root_is_safe_inside_a_container() -> None:
    # `modal deploy src/clipforge/app.py` mounts this file alone at /root/app.py.
    assert app._repo_root(Path("/root/app.py")) == Path("/")
    assert app._repo_root(Path(app.__file__).resolve()) == app.REPO_ROOT


def test_gpu_image_build_does_not_import_app() -> None:
    # run_function would import app.py in the builder, where the clipforge package isn't mounted.
    assert "run_function(" not in Path(app.__file__).read_text()


def test_face_model_is_mounted() -> None:
    assert app.CONTAINER_ENV["MODELS_DIR"] == app.MODELS_MOUNT
    assert (app.REPO_ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx").is_file()


def test_web_timeout_allows_slow_zip_downloads() -> None:
    # 257 MB took 600 s on the owner's connection and was cut off by a 10 min timeout.
    assert app.WEB_TIMEOUT_S >= 3600


def test_dispatcher_replaces_posting_tick() -> None:
    # ADR-27: sweeper, dispatcher and posting_daily are the only crons (Modal Starter allows 5)
    assert hasattr(app, "dispatcher") and not hasattr(app, "posting_tick")
    text = Path(app.__file__).read_text()
    assert text.count("schedule=modal.Cron(") == 3
    assert 'schedule=modal.Cron("*/5 * * * *")' in text


def test_dispatcher_outlasts_one_telegram_upload() -> None:
    from clipforge.bot.telegram import UPLOAD_TIMEOUT_S

    assert app.POSTING_TICK_TIMEOUT_S >= 2 * UPLOAD_TIMEOUT_S


def test_blueprints_are_mounted() -> None:
    assert app.CONTAINER_ENV["BLUEPRINTS_DIR"] == app.BLUEPRINTS_MOUNT
    assert (app.REPO_ROOT / "blueprints" / "realtalk-clips.toml").is_file()


def test_steps_service_and_api_get_the_database() -> None:
    # Task 21b: one lazy engine per container; None until DATABASE_URL is in the secret (#107)
    text = Path(app.__file__).read_text()
    assert text.count("db=_database()") == 2  # _step_deps and _service_deps
    assert "db=_database)" in text  # the API's ApiContext (called per request, cached)
    assert app._database.__wrapped__ is not None  # functools.cache
