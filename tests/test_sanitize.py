from clipforge.db.engine import DatabaseUnavailable, is_db_error
from clipforge.sanitize import clean, redact


def test_a_postgres_url_loses_user_password_and_host() -> None:
    url = "postgresql://neondb_owner:secret@ep-x.aws.neon.tech/neondb?sslmode=require"
    for message in (
        f"connect failed: {url}",
        f"connect failed: {url.replace('postgresql', 'postgres')}",
    ):
        for out, leaked in (
            (clean(message), ("neondb_owner", "secret")),
            (redact(RuntimeError(message)), ("neondb_owner", "secret", "ep-x", "neon.tech")),
        ):
            assert not any(word in out for word in leaked)


def test_userinfo_goes_for_any_scheme() -> None:
    assert "hunter2" not in clean("failed ftp://bob:hunter2@files.example.com/a")


def test_a_bot_token_path_is_cleaned() -> None:
    out = clean("GET https://api.telegram.org/file/bot123456:AAH-x_9QzA/videos/f.mp4 failed")
    assert "AAH-x_9QzA" not in out and "bot<redacted>" in out


def test_web_links_lose_only_the_query() -> None:
    assert clean("404 for https://cdn.example.com/v.mp4?sig=abc#x done") == (
        "404 for https://cdn.example.com/v.mp4 done"
    )


def test_ordinary_messages_are_unchanged() -> None:
    assert clean("ffmpeg exited with code 1") == "ffmpeg exited with code 1"
    assert clean("time=00:00:10.50 bitrate=800kb/s") == "time=00:00:10.50 bitrate=800kb/s"


def test_the_limit_is_applied() -> None:
    assert len(clean("x" * 1000)) == 300
    assert len(clean("x" * 1000, limit=50)) == 50


def test_redact_names_the_type_and_caps_at_200() -> None:
    out = redact(RuntimeError("password=s3cret " + "y" * 500))
    assert out.startswith("RuntimeError: ") and "s3cret" not in out and len(out) == 200


def test_signed_urls_lose_their_query_even_with_userinfo_or_a_bot_token() -> None:
    for text in (
        "https://u:tok@storage.example.com/v.mp4?X-Amz-Signature=abc",
        "https://api.telegram.org/file/bot1:AA/x.mp4?a=1",
    ):
        out = clean(text)
        assert "Signature" not in out and "a=1" not in out and "tok" not in out.split("@")[0]


def test_redact_drops_a_database_url_whole() -> None:
    url = "postgresql://app:pw@db.internal.example.com:5432/app?sslmode=require"
    out = redact(RuntimeError(f"failed: {url}"))
    assert out == "RuntimeError: failed: <url>"


def test_clean_leaves_file_names_and_quoted_paths_alone() -> None:
    assert clean('input "clips/clip_01.mp4" failed') == 'input "clips/clip_01.mp4" failed'
    assert clean("ep-12-guest.mp4: No such file") == "ep-12-guest.mp4: No such file"


def test_redact_still_hides_the_host_ips_and_user() -> None:
    out = redact(Exception('connection to "ep-a.neon.tech" (10.0.0.1) failed for user "owner"'))
    for leaked in ("neon.tech", "10.0.0.1", "owner"):
        assert leaked not in out


def test_is_db_error() -> None:
    from sqlalchemy.exc import OperationalError

    assert is_db_error(DatabaseUnavailable("x"))
    assert is_db_error(OperationalError("s", {}, Exception("o")))
    assert not is_db_error(ValueError("x"))
