"""`clipforge` CLI: a thin client of the deployed job API (spec §5). Needs API_URL and
API_TOKEN (from `.env`); `set-webhook` also needs the Telegram values.

    uv run clipforge run --input <url> [--n 5 --len 30-60 --lang en --perm own --credit "..."]
    uv run clipforge status [<job_id>] [--rebuild|--restore [DATE]]   # a job, or the overview
    uv run clipforge resume <job_id>
    uv run clipforge clip [videos/<channel>/ep.mp4] [--fetch]   # videos/ inbox → jobs
    uv run clipforge set-webhook
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import time
import tomllib
from collections.abc import Callable, Collection
from datetime import UTC, date, datetime
from datetime import time as dtime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from clipforge.accounts.service import AccountCreate, AccountEdit
from clipforge.bot.commands import CommandError, build_job_input
from clipforge.bot.messages import posting_overview_text, status_text
from clipforge.bot.telegram import TelegramClient
from clipforge.config import Settings, get_settings
from clipforge.inbox import (
    CHANNELS_NAME,
    LEDGER_NAME,
    OUT_DIR,
    RESERVED,
    InboxVideo,
    Ledger,
    ModalCliDownloader,
    ModalCliUploader,
    is_video,
    load_channels,
    pending,
    volume_path,
)
from clipforge.models import (
    Account,
    BackfillReport,
    CampaignRules,
    ChannelRef,
    ClipStatus,
    ImportReport,
    InboxEntry,
    JobInput,
    JobStatus,
    JobView,
    Permission,
    Platform,
    PostingOverview,
    Source,
    SourceEvent,
    SourcePermission,
    Submission,
    VerifyReport,
)
from clipforge.sources import missing_permission_fields, source_problem

_HTTP_URL = re.compile(r"https?://\S+", re.IGNORECASE)
MAX_NETWORK_ERRORS = 5  # consecutive failed polls before `wait` gives up
POLL_INTERVAL_S = 15.0  # one status check per waiting job per round (`clip --fetch`)
NO_DATABASE_DETAIL = "DATABASE_URL is not configured"  # R25 fallback trigger
NEWEST = "newest"  # `status --restore` with no DATE


class Uploader(Protocol):
    def put(self, local: Path, remote: str) -> None: ...


class Downloader(Protocol):
    def get(self, remote: str, dest: Path) -> None: ...


class ApiError(RuntimeError):
    """The API answered with an error; the message is safe to print."""

    def __init__(self, message: str, status: int | None = None, detail: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


class ApiClient:
    def __init__(self, http: httpx.Client, token: str, actor: str | None = None) -> None:
        self._http = http
        self._headers = {
            "Authorization": f"Bearer {token}",
            "X-Clipforge-Actor": actor or f"cli:{getpass.getuser()}",
        }

    def _request(self, method: str, path: str, json_body: str | None = None) -> httpx.Response:
        headers = dict(self._headers)
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        response = self._http.request(method, path, headers=headers, content=json_body)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ApiError(
                f"HTTP {response.status_code}: {detail}",
                status=response.status_code,
                detail=str(detail),
            )
        return response

    def create_job(self, job_input: JobInput) -> str:
        response = self._request("POST", "/jobs", json_body=job_input.model_dump_json())
        return str(response.json()["job_id"])

    def get_job(self, job_id: str) -> JobView:
        return JobView.model_validate(self._request("GET", f"/jobs/{job_id}").json())

    def resume(self, job_id: str) -> JobView:
        return JobView.model_validate(self._request("POST", f"/jobs/{job_id}/resume").json())

    def accounts(self) -> list[Account]:
        return [Account.model_validate(a) for a in self._request("GET", "/accounts").json()]

    def create_account(self, req: AccountCreate) -> Account:
        body = req.model_dump_json()
        return Account.model_validate(self._request("POST", "/accounts", body).json())

    def edit_account(self, account_id: str, edit: AccountEdit) -> Account:
        body = edit.model_dump_json(exclude_defaults=True)
        path = f"/accounts/{quote(account_id)}"
        return Account.model_validate(self._request("PATCH", path, body).json())

    def sources(self) -> list[Source]:
        return [Source.model_validate(s) for s in self._request("GET", "/sources").json()]

    def source(self, source_id: str) -> Source:
        return Source.model_validate(self._request("GET", f"/sources/{quote(source_id)}").json())

    def create_source(self, source: Source, imported: bool = False) -> Source:
        path = "/sources?action=imported" if imported else "/sources"
        return Source.model_validate(self._request("POST", path, source.model_dump_json()).json())

    def replace_source(self, source: Source) -> Source:
        path = f"/sources/{quote(source.id)}"
        return Source.model_validate(self._request("PUT", path, source.model_dump_json()).json())

    def source_events(self, source_id: str) -> list[SourceEvent]:
        path = f"/sources/{quote(source_id)}/events"
        return [SourceEvent.model_validate(e) for e in self._request("GET", path).json()]

    def submissions(self, source_id: str) -> list[Submission]:
        path = f"/sources/{quote(source_id)}/submissions"
        return [Submission.model_validate(x) for x in self._request("GET", path).json()]

    def posting(self) -> PostingOverview:
        return PostingOverview.model_validate(self._request("GET", "/posting").json())

    def rebuild_posting(self) -> int:
        return int(self._request("POST", "/posting/rebuild").json()["added"])

    def import_posting(self, dry_run: bool) -> ImportReport:
        path = f"/posting/import?dry_run={'true' if dry_run else 'false'}"
        return ImportReport.model_validate(self._request("POST", path).json())

    def backfill_jobs(self, dry_run: bool) -> BackfillReport:
        path = f"/jobs/backfill?dry_run={'true' if dry_run else 'false'}"
        return BackfillReport.model_validate(self._request("POST", path).json())

    def verify_posting(self) -> VerifyReport:
        return VerifyReport.model_validate(self._request("GET", "/posting/verify").json())

    def restore_posting(self, day: str | None = None) -> int:
        path = "/posting/restore" if day is None else f"/posting/restore?date={quote(day)}"
        return int(self._request("POST", path).json()["restored"])


def progress_line(view: JobView) -> str:
    line = f"{view.status} · {view.stage or 'queued'}"
    if view.progress is not None and view.status is JobStatus.RUNNING:
        line = f"{line} {view.progress.pct:.0f}%"
    if view.clips:
        done = sum(c.status is ClipStatus.DONE for c in view.clips)
        line = f"{line} · clips {done}/{len(view.clips)}"
    return line


def wait(
    get_view: Callable[[], JobView],
    *,
    interval_s: float = 5.0,
    timeout_s: float = 3600.0,
    sleep: Callable[[float], object] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    echo: Callable[[str], object] = print,
) -> JobView:
    """Poll until the job is done or failed, printing each new progress line once.

    Network errors (Wi-Fi blips, a cold start timing out) are retried; the job keeps running
    on Modal either way, so only `MAX_NETWORK_ERRORS` in a row end the wait."""
    deadline = clock() + timeout_s
    last: str | None = None
    errors = 0
    while True:
        try:
            view = get_view()
        except httpx.TransportError:
            errors += 1
            if errors >= MAX_NETWORK_ERRORS:
                raise
            sleep(interval_s)
            continue
        errors = 0
        line = progress_line(view)
        if line != last:
            echo(line)
            last = line
        if view.status in (JobStatus.DONE, JobStatus.FAILED):
            return view
        if clock() >= deadline:
            raise TimeoutError(f"job {view.job_id} still {view.status} after {timeout_s:.0f} s")
        sleep(interval_s)


def set_webhook(
    settings: Settings, client_factory: Callable[[str], TelegramClient] = TelegramClient
) -> str:
    """Point Telegram at `<API_URL>/telegram/webhook` with the secret-token header."""
    missing = [
        name
        for name, value in (
            ("API_URL", settings.api_url),
            ("TELEGRAM_BOT_TOKEN", settings.telegram_bot_token),
            ("TELEGRAM_WEBHOOK_SECRET", settings.telegram_webhook_secret),
        )
        if value is None
    ]
    if missing:
        raise SystemExit(f"set {', '.join(missing)} in .env first")
    assert settings.api_url and settings.telegram_bot_token and settings.telegram_webhook_secret
    url = f"{settings.api_url.rstrip('/')}/telegram/webhook"
    client = client_factory(settings.telegram_bot_token.get_secret_value())
    client.set_webhook(url, settings.telegram_webhook_secret.get_secret_value())
    return url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clipforge", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="submit a job and wait for it")
    run.add_argument("--input", required=True, help="direct http(s) media link (ADR-10)")
    run.add_argument("--n", help="number of clips (default: auto, by score)")
    run.add_argument("--min-score", help="auto mode: minimum score, e.g. 0.8")
    run.add_argument("--len", help="clip length range in seconds, e.g. 30-60")
    run.add_argument("--lang", help="language code, or auto")
    run.add_argument("--perm", choices=[p.value for p in Permission], help="source permission")
    run.add_argument("--credit", help="creator + license link (required for cc_by)")
    run.add_argument("--no-wait", action="store_true", help="print the job id and exit")
    clip = commands.add_parser(
        "clip", help="clip a local video (or every new one in the folder) and download the clips"
    )
    clip.add_argument("file", nargs="?", help="video file; omit to take every new video")
    clip.add_argument("--folder", default="videos", help="inbox folder (default: videos)")
    clip.add_argument("--n", help="number of clips (default: auto, by score)")
    clip.add_argument("--min-score", help="auto mode: minimum score, e.g. 0.8")
    clip.add_argument("--len", help="clip length range in seconds, e.g. 20-45")
    clip.add_argument("--lang", help="language code, or auto")
    clip.add_argument("--again", action="store_true", help="re-submit an already clipped video")
    clip.add_argument(
        "--perm",
        choices=[p.value for p in Permission],
        help="source permission (default: the channel's, or DEFAULT_PERMISSION)",
    )
    clip.add_argument(
        "--fetch",
        action="store_true",
        help="wait for the jobs and download the clips into <folder>/out/",
    )
    clip.add_argument("--no-wait", action="store_true", help="(default now) submit and exit")
    status = commands.add_parser("status", help="a job's status, or the posting overview")
    status.add_argument("job_id", nargs="?")
    status.add_argument(
        "--rebuild", action="store_true", help="re-queue every finished channel job for posting"
    )
    status.add_argument(
        "--restore",
        nargs="?",
        const=NEWEST,
        metavar="DATE",
        help="put back posting keys that expired, from the Volume snapshot of DATE "
        "(YYYY-MM-DD, UTC; default: the newest)",
    )
    commands.add_parser("resume").add_argument("job_id")
    commands.add_parser("set-webhook", help="register the Telegram webhook")
    _add_account_parser(commands)
    _add_source_parser(commands)
    posting = commands.add_parser("posting", help="posting queue: move the Dict queue to Postgres")
    pacts = posting.add_subparsers(dest="action", required=True)
    pacts.add_parser("import").add_argument("--dry-run", action="store_true")
    pacts.add_parser("verify")
    jobs = commands.add_parser("jobs", help="job records")
    jacts = jobs.add_subparsers(dest="action", required=True)
    jacts.add_parser("backfill").add_argument("--dry-run", action="store_true")
    return parser


def _add_account_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    account = commands.add_parser("account", help="accounts: blueprint + language + handles")
    acts = account.add_subparsers(dest="action", required=True)
    create = acts.add_parser("create")
    create.add_argument("--blueprint", required=True)
    create.add_argument("--lang", required=True, choices=["en", "es"])
    create.add_argument("--handle", required=True)
    create.add_argument("--id")
    create.add_argument(
        "--posting-from-env", action="store_true", help="start from the POSTING_* settings"
    )
    edit = acts.add_parser("edit")
    edit.add_argument("account_id")
    edit.add_argument("--handle", action="append", default=[], metavar="PLATFORM=HANDLE")
    chat = edit.add_mutually_exclusive_group()
    chat.add_argument("--chat", type=int, help="the Telegram chat that receives the clips")
    chat.add_argument("--clear-chat", action="store_true")
    edit.add_argument("--slots", help="comma-separated, e.g. 8:00,12:30")
    edit.add_argument("--timezone")
    edit.add_argument("--hashtags", help="comma-separated")
    edit.add_argument("--review-tier", choices=["review", "sample", "auto"])
    acts.add_parser("list")


def _add_source_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    source = commands.add_parser("source", help="sources: the database is the only copy (S1)")
    sacts = source.add_subparsers(dest="action", required=True)
    add = sacts.add_parser("add")
    add.add_argument("source_id")
    add.add_argument("--account", required=True)
    add.add_argument("--credit", required=True, help="credit text shown in captions")
    add.add_argument("--permission", required=True, choices=[p.value for p in Permission])
    edit = sacts.add_parser("edit")
    edit.add_argument("source_id")
    edit.add_argument("--account")
    edit.add_argument("--credit")
    edit.add_argument("--permission", choices=[p.value for p in Permission])
    edit.add_argument("--status", choices=["active", "paused", "ended"])
    edit.add_argument("--no-expiry", action="store_true")
    for parser in (add, edit):
        parser.add_argument("--kind", choices=["channel", "campaign", "own"])
        parser.add_argument("--url")
        parser.add_argument("--handle", action="append", default=[], metavar="PLATFORM=HANDLE")
        parser.add_argument("--granted-at", metavar="YYYY-MM-DD")
        parser.add_argument("--granted-by")
        parser.add_argument("--evidence-url")
        parser.add_argument("--platforms", help="comma-separated; default all four")
        parser.add_argument("--monetization", choices=["yes", "no"])
        parser.add_argument("--translation", choices=["yes", "no"])
        parser.add_argument("--expires", metavar="YYYY-MM-DD")
        parser.add_argument("--restrictions")
        parser.add_argument("--notes")
        parser.add_argument("--rules")
        parser.add_argument("--tag", action="append", default=[])
        parser.add_argument("--link", action="append", default=[])
        parser.add_argument("--deadline", metavar="YYYY-MM-DD")
        parser.add_argument("--rate-per-1k", type=float)
        parser.add_argument("--submission-url")
        parser.add_argument("--not-sponsored", action="store_true")
    sacts.add_parser("list")
    sacts.add_parser("show").add_argument("source_id")
    sacts.add_parser("submissions").add_argument("source_id")
    imp = sacts.add_parser("import-toml", help="one-off: videos/channels.toml -> sources")
    imp.add_argument("--folder", default="videos")
    imp.add_argument("--account", help="for entries without an `account` key")
    imp.add_argument("--dry-run", action="store_true")


def _finish(view: JobView) -> int:
    if view.status is JobStatus.DONE:
        done = sum(c.status is ClipStatus.DONE for c in view.clips)
        print(f"done · {done} of {len(view.clips)} clips · ${view.cost.total_usd:.3f}")
        print(view.download_url or "(no download link: API_URL / DOWNLOAD_SIGNING_KEY unset)")
        return 0
    error = view.error
    where = f"{error.stage}: {error.message}" if error else str(view.stage)
    print(f"failed at {where}\nclipforge resume {view.job_id}")
    return 1


def main(
    argv: list[str] | None = None,
    *,
    http: httpx.Client | None = None,
    settings: Settings | None = None,
    sleep: Callable[[float], object] = time.sleep,
    uploader: Uploader | None = None,
    downloader: Downloader | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    settings = settings or get_settings()
    if args.command == "set-webhook":
        print(f"webhook set: {set_webhook(settings)}")
        return 0
    if settings.api_token is None or (http is None and settings.api_url is None):
        print("set API_URL and API_TOKEN in .env (see .env.example)", file=sys.stderr)
        return 2
    http = http or httpx.Client(base_url=str(settings.api_url), timeout=30.0)
    client = ApiClient(http, settings.api_token.get_secret_value())
    try:
        if args.command == "run":
            return _run(args, settings, client, sleep)
        if args.command == "clip":
            return _clip(
                args,
                settings,
                client,
                sleep,
                uploader or ModalCliUploader(),
                downloader or ModalCliDownloader(),
            )
        if args.command == "account":
            return _account(args, client)
        if args.command == "source":
            if args.action == "import-toml":
                importer = ApiClient(http, settings.api_token.get_secret_value(), "import-toml")
                return _import_toml(args, importer)
            return _source(args, client)
        if args.command == "posting":
            return _posting_migration(args, client)
        if args.command == "jobs":
            backfill = client.backfill_jobs(args.dry_run)
            print(backfill.model_dump_json(indent=2))
            return 1 if backfill.failed else 0
        if args.command == "status":
            if args.rebuild:
                print(f"added {client.rebuild_posting()} clip(s) to the posting queue")
            elif args.restore is not None:
                day = None if args.restore == NEWEST else args.restore
                restored = client.restore_posting(day)
                which = "the newest" if day is None else f"the {day}"
                print(f"restored {restored} posting key(s) from {which} snapshot")
            elif args.job_id is None:
                print(posting_overview_text(client.posting(), settings.posting_timezone))
            else:
                print(status_text(client.get_job(args.job_id)))
            return 0
        print(status_text(client.resume(args.job_id)))
        return 0
    except ApiError as exc:
        print(exc, file=sys.stderr)
        return 1
    except TimeoutError as exc:
        print(exc, file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"network error talking to the API: {type(exc).__name__}", file=sys.stderr)
        return 1


def _posting_migration(args: argparse.Namespace, client: ApiClient) -> int:
    if args.action == "verify":
        verify = client.verify_posting()
        print(verify.model_dump_json(indent=2))
        return 1 if verify.differences > 0 else 0
    imported = client.import_posting(args.dry_run)
    print(imported.model_dump_json(indent=2))
    return 1 if imported.failed else 0


def _run(
    args: argparse.Namespace,
    settings: Settings,
    client: ApiClient,
    sleep: Callable[[float], object],
) -> int:
    if not _HTTP_URL.fullmatch(args.input):
        print("--input must be a direct http(s) media link (ADR-10)", file=sys.stderr)
        return 2
    options = {
        key: value
        for key, value in (
            ("n", args.n),
            ("score", args.min_score),
            ("len", args.len),
            ("lang", args.lang),
            ("perm", args.perm),
            ("credit", args.credit),
        )
        if value is not None
    }
    try:
        job_input = build_job_input(settings, options, None, url=args.input)
    except CommandError as exc:
        print(exc, file=sys.stderr)
        return 2
    job_id = client.create_job(job_input)
    print(f"job {job_id}")
    if args.no_wait:
        return 0
    return _finish(wait(lambda: client.get_job(job_id), sleep=sleep))


class JobReader(Protocol):
    def get_job(self, job_id: str) -> JobView: ...


class UnknownSource(ValueError):
    """A video sits in a subfolder of the inbox that has no source."""

    def __init__(self, slug: str) -> None:
        super().__init__(slug)
        self.slug = slug


def _video_for(folder: Path, path: Path, known: Collection[str]) -> InboxVideo:
    """A video named on the command line: a source's video when it sits in a source folder.
    Paths are compared without following symlinks, so the key matches `inbox_videos`. Raises
    UnknownSource for a subfolder of the inbox that has no source (a typo in the name)."""
    parent = Path(os.path.abspath(path)).parent
    if parent.parent == Path(os.path.abspath(folder)) and not parent.name.startswith("."):
        if parent.name in known:
            return InboxVideo(path, f"{parent.name}/{path.name}", parent.name)
        if parent.name not in RESERVED:
            raise UnknownSource(parent.name)
    return InboxVideo(path, path.name, None)


def _no_source_message(folder: Path, slug: str) -> str:
    return (
        f'{folder}/{slug}/: no source "{slug}".\n'
        "Add it with:\n"
        f'    clipforge source add {slug} --account <account> --credit "<credit name>" '
        "--permission <type>\n"
        f"or, once, import {folder}/{CHANNELS_NAME} with: "
        "clipforge source import-toml --account <account>"
    )


def _job_input(
    settings: Settings,
    options: dict[str, str],
    video: InboxVideo,
    sources: dict[str, Source],
    remote: str,
) -> JobInput:
    """Source videos carry their source's id, credit and permission (ADR-22, spec §6.3)."""
    options = dict(options)
    update: dict[str, object] = {"source_label": video.path.stem}
    if video.channel is not None:
        source = sources[video.channel]
        options.setdefault("perm", source.permission.type.value)
        options["credit"] = source.credit_name
        update["channel"] = ChannelRef(slug=source.id, name=source.credit_name)
    return build_job_input(settings, options, None, source_path=remote).model_copy(update=update)


def _transition_sources_from_toml(folder: Path) -> dict[str, Source]:
    """TRANSITION (ruling R25): remove after the S1 rollout is verified, together with the 503
    branch in `_clip`. While the deployed API has no database, `clipforge clip` reads
    <folder>/channels.toml as before; each Channel becomes a Source with the same credit and
    permission, so the job input is unchanged. Raises ValueError when the file is invalid."""
    sources: dict[str, Source] = {}
    for slug, channel in load_channels(folder / CHANNELS_NAME).items():
        sources[slug] = Source(
            id=slug,
            account_id="legacy",
            kind="own" if channel.permission is Permission.OWN else "channel",
            credit_name=channel.name,
            permission=SourcePermission(type=channel.permission),
        )
    return sources


def _sources_or_transition_fallback(folder: Path, client: ApiClient) -> dict[str, Source] | None:
    """The database's sources; `None` when the API has no database yet (R25), in which case the
    caller uses `_transition_sources_from_toml`. An unreachable API raises here, before any
    upload. Any other API error propagates."""
    try:
        return {s.id: s for s in client.sources()}
    except ApiError as exc:
        if exc.status != 503 or exc.detail != NO_DATABASE_DETAIL:
            raise
        return None


def _clip(
    args: argparse.Namespace,
    settings: Settings,
    client: ApiClient,
    sleep: Callable[[float], object],
    uploader: Uploader,
    downloader: Downloader,
) -> int:
    """Upload and submit every new video (source folders included), then exit. With
    `--fetch`, also wait for every submitted job and download its clips."""
    folder = Path(args.folder)
    found = _sources_or_transition_fallback(folder, client)
    if found is None:
        print(
            f"warning: the API has no database yet; using {folder}/{CHANNELS_NAME} until the "
            "S1 rollout (then run: clipforge source import-toml)",
            file=sys.stderr,
        )
        try:
            sources = _transition_sources_from_toml(folder)
        except ValueError as exc:
            print(f"{folder / CHANNELS_NAME}: {exc}", file=sys.stderr)
            return 2
    else:
        sources = found
        if (folder / CHANNELS_NAME).exists():
            print(
                f"warning: {folder / CHANNELS_NAME} is no longer read; sources live in the "
                "database (clipforge source list). Delete it after checking the import.",
                file=sys.stderr,
            )
    try:
        ledger = Ledger(folder / LEDGER_NAME)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.file is not None:
        path = Path(args.file)
        if not is_video(path):
            print(f"{path}: not a video file (.mp4 .mov .mkv .webm .m4v .avi)", file=sys.stderr)
            return 2
        try:
            video = _video_for(folder, path, sources)
        except UnknownSource as exc:
            if found is None:  # R25 fallback: the old message
                print(f"{path}: {exc.slug}/: not in {CHANNELS_NAME}, skipped", file=sys.stderr)
            else:
                print(_no_source_message(folder, exc.slug), file=sys.stderr)
            return 2
        previous = ledger.job_id(video.key)
        if previous is not None and not args.again:
            print(f"{video.key} was already submitted as job {previous}; use --again to re-cut",
                  file=sys.stderr)  # fmt: skip
            return 2
        videos = [video]
    else:
        folder.mkdir(parents=True, exist_ok=True)
        videos, unknown = pending(folder, ledger, sources)
        if unknown and found is None:  # R25 fallback: warn and carry on, as before
            for slug in unknown:
                print(f"warning: {slug}/: not in {CHANNELS_NAME}, skipped", file=sys.stderr)
        elif unknown:
            for slug in unknown:
                print(_no_source_message(folder, slug), file=sys.stderr)
            return 2
        if not videos and not (args.fetch and ledger.submitted()):
            print(f"no new videos in {folder}/ (drop .mp4/.mov/... files there)")
            return 0

    options = {
        key: value
        for key, value in (
            ("n", args.n),
            ("score", args.min_score),
            ("len", args.len),
            ("lang", args.lang),
            ("perm", args.perm),
        )
        if value is not None
    }
    now = datetime.now(UTC)
    held: set[str] = set()
    submitted = 0
    for video in videos:
        if video.channel is not None:
            if video.channel in held:
                continue
            reason = source_problem(sources[video.channel], now)
            if reason is not None:
                held.add(video.channel)
                print(
                    f"warning: {video.channel}: {reason}; its videos are skipped", file=sys.stderr
                )
                continue
        remote = volume_path(video.path)
        try:
            job_input = _job_input(settings, options, video, sources, remote)
        except CommandError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"uploading {video.key} ...", flush=True)
        uploader.put(video.path, remote)
        job_id = client.create_job(job_input)
        ledger.record(video.key, job_id)
        submitted += 1
        print(f"{video.key}: job {job_id}")
    if not args.fetch:
        if submitted:
            print(f"{submitted} submitted; clips reach Telegram as they're ready "
                  "(or run `clipforge clip --fetch` to download them)")  # fmt: skip
        return 0
    return _fetch(ledger.submitted(), ledger, folder, client, sleep, downloader)


def _fetch(
    keys: list[str],
    ledger: Ledger,
    folder: Path,
    client: JobReader,
    sleep: Callable[[float], object],
    downloader: Downloader,
) -> int:
    """Check each job in turn until every one is done or failed, downloading each done job
    right away. Failed jobs stay `submitted`, so `clipforge resume` + `--fetch` still works.
    Safe to interrupt."""
    left = list(keys)
    last: dict[str, str] = {}
    failed_rounds = 0  # consecutive rounds in which every poll hit a network/server error
    code = 0
    while left:
        reached = False
        for key in list(left):
            entry = ledger.get(key)
            assert entry is not None
            try:
                view = client.get_job(entry.job_id)
            except httpx.TransportError:
                continue
            except ApiError as exc:
                if exc.status == 404:
                    print(f"{key}: job {entry.job_id} not found on the API; skipping")
                    left.remove(key)
                    code = 1
                    reached = True
                    continue
                if exc.status is not None and (exc.status >= 500 or exc.status == 429):
                    continue  # the API is busy or deploying: try again next round
                raise  # e.g. 401: a config problem, reported by main
            reached = True
            line = progress_line(view)
            if last.get(key) != line:
                print(f"{key}: {line}", flush=True)
                last[key] = line
            if view.status is JobStatus.DONE:
                dest = _out_dir(folder, key)
                print(f"{key}: downloading the clips into {dest}/ ...", flush=True)
                downloader.get(f"{entry.job_id}/output", dest)
                out = dest.relative_to(folder / OUT_DIR).as_posix()
                ledger.update(key, InboxEntry(job_id=entry.job_id, status="fetched", out=out))
                left.remove(key)
            elif view.status is JobStatus.FAILED:
                error = view.error
                where = f"{error.stage}: {error.message}" if error else "unknown error"
                print(f"{key}: failed at {where} · clipforge resume {entry.job_id}")
                left.remove(key)
                code = 1
        failed_rounds = 0 if reached else failed_rounds + 1
        if failed_rounds >= MAX_NETWORK_ERRORS:
            raise httpx.TransportError("the API was unreachable for several rounds")
        if left:
            sleep(POLL_INTERVAL_S)
    return code


def _out_dir(folder: Path, key: str) -> Path:
    """`<folder>/out/[<channel>/]<video stem>/`, or `-2/`, `-3/`... so a re-cut never
    overwrites."""
    base = folder / OUT_DIR / Path(key).with_suffix("")
    candidate, n = base, 1
    while candidate.exists() and any(candidate.iterdir()):
        n += 1
        candidate = base.with_name(f"{base.name}-{n}")
    return candidate


# ---- accounts and sources -------------------------------------------------------------------


def _parse_handles(values: list[str]) -> dict[Platform, str]:
    """`--handle tiktok=@name` (repeatable). Raises ValueError with the message to print."""
    handles: dict[Platform, str] = {}
    for value in values:
        platform, sep, handle = value.partition("=")
        try:
            if not sep or not handle:
                raise ValueError
            handles[Platform(platform.strip().lower())] = handle.strip()
        except ValueError:
            raise ValueError("--handle expects PLATFORM=HANDLE") from None
    return handles


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _account_line(account: Account) -> str:
    handles = " ".join(f"{p}={prof.handle}" for p, prof in account.platforms.items())
    return (f"{account.id}  {account.kind}  {account.language}  {account.review_tier}  "
            f"{handles}")  # fmt: skip


def _account(args: argparse.Namespace, client: ApiClient) -> int:
    if args.action == "list":
        for account in client.accounts():
            print(_account_line(account))
        return 0
    try:
        if args.action == "create":
            account = client.create_account(
                AccountCreate(
                    blueprint=args.blueprint,
                    language=args.lang,
                    handle=args.handle,
                    id=args.id,
                    posting_from_env=args.posting_from_env,
                )
            )
            print(f"created {_account_line(account)}")
            return 0
        edit = AccountEdit(
            handles=_parse_handles(args.handle),
            chat_id=args.chat,
            clear_chat=args.clear_chat,
            slots=_csv(args.slots) if args.slots is not None else None,
            timezone=args.timezone,
            hashtags=_csv(args.hashtags) if args.hashtags is not None else None,
            review_tier=args.review_tier,
        )
    except (ValueError, ValidationError) as exc:
        print(exc, file=sys.stderr)
        return 2
    print(f"updated {_account_line(client.edit_account(args.account_id, edit))}")
    return 0


def _end_of_day(value: str, flag: str) -> datetime:
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{flag} expects YYYY-MM-DD") from None
    return datetime.combine(day, dtime(23, 59, 59), tzinfo=UTC)


def _yes_no(value: str | None) -> bool | None:
    return None if value is None else value == "yes"


def _source_from_args(args: argparse.Namespace, base: Source | None) -> Source:
    """Merge the flags that were given onto `base` (edit) or build a new source (add). The
    model validators run on the result. Raises ValueError/ValidationError."""
    data: dict[str, object] = (
        base.model_dump() if base else {"id": args.source_id, "permission": {}}
    )
    permission = dict(data["permission"])  # type: ignore[call-overload]
    if getattr(args, "permission", None):
        permission["type"] = args.permission
    if args.granted_at:
        try:
            permission["granted_at"] = date.fromisoformat(args.granted_at)
        except ValueError:
            raise ValueError("--granted-at expects YYYY-MM-DD") from None
    for flag, key in (("granted_by", "granted_by"), ("evidence_url", "evidence_url"),
                      ("restrictions", "restrictions")):  # fmt: skip
        if getattr(args, flag) is not None:
            permission[key] = getattr(args, flag)
    if args.platforms:
        permission["platforms"] = _csv(args.platforms)
    for flag, key in (("monetization", "monetization_allowed"),
                      ("translation", "translation_allowed")):  # fmt: skip
        if getattr(args, flag) is not None:
            permission[key] = _yes_no(getattr(args, flag))
    if args.expires:
        permission["expires_at"] = _end_of_day(args.expires, "--expires")
    if getattr(args, "no_expiry", False):
        permission["expires_at"] = None
    data["permission"] = permission

    for flag, key in (("account", "account_id"), ("credit", "credit_name"), ("kind", "kind"),
                      ("status", "status"), ("url", "url"), ("notes", "notes")):  # fmt: skip
        if getattr(args, flag, None) is not None:
            data[key] = getattr(args, flag)
    if args.handle:
        data["creator_handles"] = {**(data.get("creator_handles") or {}),  # type: ignore[dict-item]
                                   **_parse_handles(args.handle)}  # fmt: skip

    campaign = dict(data["campaign"]) if data.get("campaign") else {}  # type: ignore[call-overload]
    for flag, key in (("rules", "rules"), ("rate_per_1k", "rate_per_1k"),
                      ("submission_url", "submission_url")):  # fmt: skip
        if getattr(args, flag) is not None:
            campaign[key] = getattr(args, flag)
    if args.tag:
        campaign["required_tags"] = list(args.tag)
    if args.link:
        campaign["required_links"] = list(args.link)
    if args.deadline:
        campaign["deadline"] = _end_of_day(args.deadline, "--deadline")
    if args.not_sponsored:
        campaign["sponsored"] = False
    data["campaign"] = CampaignRules.model_validate(campaign).model_dump() if campaign else None
    return Source.model_validate(data)


def _source_line(source: Source, now: datetime) -> str:
    expires = source.permission.expires_at
    note = ""
    if expires is not None:
        days = (expires - now).days
        note = (
            f"  ⚠ expired {expires:%Y-%m-%d}"
            if days < 0
            else f"  ⚠ expires in {days} days"
            if days <= 14
            else f"  expires {expires:%Y-%m-%d}"
        )
    return (f"{source.id}  {source.account_id}  {source.kind}  {source.status}  "
            f"{source.permission.type}{note}")  # fmt: skip


def _source(args: argparse.Namespace, client: ApiClient) -> int:
    action = args.action
    if action == "list":
        now = datetime.now(UTC)
        for source in client.sources():
            print(_source_line(source, now))
        return 0
    if action == "show":
        source = client.source(args.source_id)
        print(source.model_dump_json(indent=2))
        missing = missing_permission_fields(source)
        print(f"not recorded: {', '.join(missing)}" if missing else "permission record complete")
        for event in sorted(client.source_events(args.source_id), key=lambda e: e.at, reverse=True):
            print(f"{event.at:%Y-%m-%d %H:%M}  {event.action} by {event.actor}")
        return 0
    if action == "submissions":
        for sub in client.submissions(args.source_id):
            print(f"{sub.posted_at:%Y-%m-%d %H:%M}  {sub.platform}  {sub.item_id}  {sub.url or ''}")
        return 0
    try:
        if action == "add":
            source = _source_from_args(args, None)
        else:
            source = _source_from_args(args, client.source(args.source_id))
    except (ValueError, ValidationError) as exc:  # ValidationError is a ValueError
        print(exc, file=sys.stderr)
        return 2
    saved = client.create_source(source) if action == "add" else client.replace_source(source)
    print(f"{'added' if action == 'add' else 'updated'} {_source_line(saved, datetime.now(UTC))}")
    return 0


def _import_toml(args: argparse.Namespace, client: ApiClient) -> int:
    """One-off: videos/channels.toml -> source rows. Idempotent: existing ids are skipped."""
    path = Path(args.folder) / CHANNELS_NAME
    try:
        channels = load_channels(path)
    except ValueError as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return 2
    if not channels:
        print(f"{path}: nothing to import")
        return 0
    raw = tomllib.loads(path.read_text())
    existing = {s.id for s in client.sources()}
    failed = 0
    for slug, channel in channels.items():
        account = raw[slug].get("account") or args.account
        if slug in existing:
            print(f"skipped {slug}: already a source")
            continue
        if not account:
            print(f'failed {slug}: no account (add `account = "..."` or pass --account)',
                  file=sys.stderr)  # fmt: skip
            failed += 1
            continue
        kind = raw[slug].get("kind", "own" if channel.permission is Permission.OWN else "channel")
        try:
            source = Source.model_validate({
                "id": slug, "account_id": account, "kind": kind, "credit_name": channel.name,
                "url": str(channel.url) if channel.url else None,
                "permission": {"type": channel.permission},
                "campaign": raw[slug].get("campaign"),
            })  # fmt: skip
        except ValidationError as exc:
            print(f"failed {slug}: {exc}", file=sys.stderr)
            failed += 1
            continue
        verb = "would import" if args.dry_run else "imported"
        if not args.dry_run:
            try:
                client.create_source(source, imported=True)
            except ApiError as exc:
                if exc.status != 409:
                    raise
                print(f"skipped {slug}: already a source")  # added since the list was read
                continue
        missing = ", ".join(missing_permission_fields(source))
        print(f"{verb} {slug} -> {account}; not recorded yet: {missing}\n"
              f"  fill in with: clipforge source edit {slug} --granted-at ... --granted-by ... "
              f"--evidence-url ... --monetization yes|no --translation yes|no")  # fmt: skip
    if not args.dry_run:
        print(f"{path} is no longer read. Check `clipforge source list`, then delete it.")
    return 1 if failed else 0
