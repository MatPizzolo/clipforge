"""Job API (spec §5): the entry point for the CLI, curl and the Telegram webhook (ADR-2).

Routes are sync, so FastAPI runs them in worker threads: the Modal Dict/Function calls block,
and the Telegram bridge uses `asyncio.run`, which needs a thread without a running loop.
"""

from __future__ import annotations

import datetime as dt
import hmac
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import httpx
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from telegram.error import TelegramError

from clipforge.accounts.autopilot import AutopilotError, AutopilotService, describe
from clipforge.accounts.autopilot import UnknownAccount as UnknownAutopilotAccount
from clipforge.accounts.service import (
    AccountCreate,
    AccountEdit,
    AccountError,
    create_account,
    edit_account,
)
from clipforge.actors import ACTOR, is_system
from clipforge.bot.telegram import TelegramSender
from clipforge.bot.webhook import BotContext, handle_update
from clipforge.config import Settings
from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database, DatabaseUnavailable, is_db_error, redact
from clipforge.db.sources import SourceExists, SourcesRepo, UnknownAccount, UnknownSource
from clipforge.jobs import is_job_id, utcnow
from clipforge.links import verify, with_download_url
from clipforge.models import (
    ACCOUNT_ID,
    Account,
    AutopilotChange,
    AutopilotView,
    BackfillReport,
    ImportReport,
    JobInput,
    JobView,
    PolicyDryRun,
    PostingOverview,
    Source,
    SourceEvent,
    Submission,
    VerifyReport,
)
from clipforge.pipeline.steps import Deps, JobNotResumable
from clipforge.policy.checks import dry_run
from clipforge.posting import migrate
from clipforge.posting.backend import posting_of
from clipforge.service import (
    PostingOutage,
    create_job,
    get_job_view,
    posting_overview,
    rebuild_posting,
    restore_posting,
    resume_job,
)

log = logging.getLogger(__name__)


@dataclass
class ApiContext:
    settings: Settings
    deps: Callable[[], Deps]  # built lazily, once per container
    sender: Callable[[], TelegramSender | None]
    db: Callable[[], Database | None] = lambda: None  # Postgres; None answers 503


def actor(x_clipforge_actor: Annotated[str | None, Header()] = None) -> str:
    """Who made a change, for source_events (informational: the bearer token is the auth)."""
    return (x_clipforge_actor or "api").strip()[:80] or "api"


def person(x_clipforge_actor: Annotated[str | None, Header()] = None) -> str:
    """The person making an autopilot change: `web:<login>` from the dashboard or the CLI's
    `cli:<user>`. Never anonymous and never `system:` from outside."""
    who = (x_clipforge_actor or "").strip()
    if not ACTOR.fullmatch(who) or is_system(who):
        raise HTTPException(400, "X-Clipforge-Actor must name the person (web:<login>, cli:<user>)")
    return who


def _same(given: str | None, expected: str) -> bool:
    return hmac.compare_digest((given or "").encode(), expected.encode())


def create_app(ctx: ApiContext) -> FastAPI:
    settings = ctx.settings
    app = FastAPI(title="ClipForge", docs_url=None, redoc_url=None, openapi_url=None)

    def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
        if settings.api_token is None:
            raise HTTPException(503, "API_TOKEN is not configured")
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not _same(token, settings.api_token.get_secret_value()):
            raise HTTPException(
                401, "invalid or missing bearer token", headers={"WWW-Authenticate": "Bearer"}
            )

    authorized = [Depends(require_token)]

    @app.exception_handler(DatabaseUnavailable)
    def _unavailable(request: Request, exc: DatabaseUnavailable) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    @app.exception_handler(PoolTimeout)
    def _db_down(request: Request, exc: Exception) -> JSONResponse:
        log.warning("database error: %s", redact(exc))
        return JSONResponse({"detail": "database unavailable"}, status_code=503)

    def database() -> Database:
        found = ctx.db()
        if found is None:
            raise DatabaseUnavailable("DATABASE_URL is not configured")
        return found

    def slug(value: str) -> str:
        if not re.fullmatch(ACCOUNT_ID, value):
            raise HTTPException(404, "not found")
        return value

    @app.post("/accounts", status_code=201, dependencies=authorized)
    def post_account(req: AccountCreate, who: Annotated[str, Depends(actor)]) -> Account:
        try:
            return create_account(
                AccountsRepo(database()),
                settings,
                req,
                utcnow(),
                kv=ctx.deps().store.kv,
                actor=who,
            )
        except AccountError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/accounts", dependencies=authorized)
    def get_accounts() -> list[Account]:
        return AccountsRepo(database()).list()

    @app.get("/accounts/{account_id}", dependencies=authorized)
    def get_account(account_id: str) -> Account:
        wanted = slug(account_id)
        found = AccountsRepo(database()).get(wanted)
        if found is None:
            raise HTTPException(404, "unknown account")
        return found

    @app.patch("/accounts/{account_id}", dependencies=authorized)
    def patch_account(account_id: str, edit: AccountEdit) -> Account:
        wanted = slug(account_id)
        try:
            return edit_account(
                AccountsRepo(database()), settings, wanted, edit, utcnow(), kv=ctx.deps().store.kv
            )
        except AccountError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.post("/sources", status_code=201, dependencies=authorized)
    def post_source(
        source: Source, who: Annotated[str, Depends(actor)],
        action: Literal["created", "imported"] = "created",
    ) -> Source:  # fmt: skip
        try:
            SourcesRepo(database()).create(source, who, utcnow(), action)
        except SourceExists as exc:
            raise HTTPException(409, str(exc)) from None
        except UnknownAccount as exc:
            raise HTTPException(400, str(exc)) from None
        return source

    @app.put("/sources/{source_id}", dependencies=authorized)
    def put_source(source_id: str, source: Source, who: Annotated[str, Depends(actor)]) -> Source:
        if source.id != slug(source_id):
            raise HTTPException(400, "the path and body ids differ")
        try:
            SourcesRepo(database()).replace(source, who, utcnow())
        except UnknownSource:
            raise HTTPException(404, "unknown source") from None
        except UnknownAccount as exc:
            raise HTTPException(400, str(exc)) from None
        return source

    @app.get("/sources", dependencies=authorized)
    def get_sources() -> list[Source]:
        return SourcesRepo(database()).list()

    @app.get("/sources/{source_id}", dependencies=authorized)
    def get_source(source_id: str) -> Source:
        wanted = slug(source_id)
        found = SourcesRepo(database()).get(wanted)
        if found is None:
            raise HTTPException(404, "unknown source")
        return found

    @app.get("/sources/{source_id}/events", dependencies=authorized)
    def get_source_events(source_id: str) -> list[SourceEvent]:
        wanted = slug(source_id)
        return SourcesRepo(database()).events(wanted)

    @app.get("/sources/{source_id}/submissions", dependencies=authorized)
    def get_submissions(source_id: str) -> list[Submission]:
        wanted = slug(source_id)
        return SourcesRepo(database()).submissions(wanted)

    def reload(deps: Deps) -> None:
        try:
            deps.volume.reload()
        except Exception:
            log.warning("volume reload failed; serving possibly stale files", exc_info=True)

    def view(job_id: str) -> JobView:
        if not is_job_id(job_id):
            raise HTTPException(404, "unknown job")
        deps = ctx.deps()
        reload(deps)
        try:
            found = get_job_view(deps.store, deps.root, job_id, deps.jobs_db)
        except KeyError:
            raise HTTPException(404, "unknown job") from None
        return with_download_url(found, settings)

    @app.post("/jobs", status_code=201, dependencies=authorized)
    def post_job(job_input: JobInput) -> dict[str, str]:
        return {"job_id": create_job(ctx.deps(), job_input).job_id}

    @app.post("/jobs/backfill", dependencies=authorized)
    def post_jobs_backfill(dry_run: bool = False) -> BackfillReport:
        deps = ctx.deps()
        reload(deps)
        return migrate.backfill_jobs(deps.store.kv, deps.root, database(), dry_run)

    @app.get("/jobs/{job_id}", dependencies=authorized)
    def get_job(job_id: str) -> JobView:
        return view(job_id)

    @app.get("/posting", dependencies=authorized)
    def get_posting() -> PostingOverview:
        return posting_overview(ctx.deps(), settings, utcnow())

    @app.post("/posting/rebuild", dependencies=authorized)
    def post_posting_rebuild() -> dict[str, int]:
        deps = ctx.deps()
        reload(deps)
        try:
            return {"added": rebuild_posting(deps, utcnow())}
        except PostingOutage as exc:
            raise HTTPException(409, str(exc)) from None

    @app.post("/posting/import", dependencies=authorized)
    def post_posting_import(dry_run: bool = False) -> ImportReport:
        deps = ctx.deps()
        reload(deps)
        return migrate.import_posting(
            deps.store.kv, deps.root, database(), settings.posting_account_id, dry_run
        )

    @app.get("/posting/verify", dependencies=authorized)
    def get_posting_verify() -> VerifyReport:
        return migrate.verify_posting(ctx.deps().store.kv, database(), settings.posting_account_id)

    @app.post("/posting/restore", dependencies=authorized)
    def post_posting_restore(date: str | None = None) -> dict[str, int]:
        day = None
        if date is not None:
            try:
                day = dt.date.fromisoformat(date)
            except ValueError:
                raise HTTPException(400, "date must be YYYY-MM-DD") from None
        deps = ctx.deps()
        reload(deps)
        return {"restored": restore_posting(deps, day)}

    @app.post("/jobs/{job_id}/resume", dependencies=authorized)
    def post_resume(job_id: str) -> JobView:
        if not is_job_id(job_id):
            raise HTTPException(404, "unknown job")
        try:
            resume_job(ctx.deps(), job_id)
        except KeyError:
            raise HTTPException(404, "unknown job") from None
        except JobNotResumable as exc:
            raise HTTPException(409, str(exc)) from None
        return view(job_id)

    @app.get("/jobs/{job_id}/download")
    def download(job_id: str, exp: int, sig: str) -> FileResponse:
        if settings.download_signing_key is None:
            raise HTTPException(503, "DOWNLOAD_SIGNING_KEY is not configured")
        key = settings.download_signing_key.get_secret_value()
        if not is_job_id(job_id) or not verify(key, job_id, exp, sig):
            raise HTTPException(403, "invalid or expired link")
        found = view(job_id)
        deps = ctx.deps()
        root = deps.root.resolve()
        path = (root / found.output_zip).resolve() if found.output_zip else None
        if path is None or not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404, "zip not found")
        return FileResponse(path, media_type="application/zip", filename=f"clipforge-{job_id}.zip")

    # ---- S2a admin routes (bearer token; they move to the `admin` endpoint in S3-1, ADR-38)

    def autopilot_service() -> AutopilotService:
        db = database()
        return AutopilotService(db, AccountsRepo(db), ctx.deps().store.kv)

    def autopilot_view(svc: AutopilotService, account_id: str) -> AutopilotView:
        ap = svc.get(account_id)
        return AutopilotView(autopilot=ap, label=describe(ap),
                             waiting_on=svc.waiting_on(account_id),
                             history=svc.history(account_id))  # fmt: skip

    @app.get("/admin/accounts/{account_id}/autopilot", dependencies=authorized)
    def get_autopilot(account_id: str) -> AutopilotView:
        wanted = slug(account_id)
        try:
            return autopilot_view(autopilot_service(), wanted)
        except UnknownAutopilotAccount:
            raise HTTPException(404, "unknown account") from None

    @app.put("/admin/accounts/{account_id}/autopilot", dependencies=authorized)
    def put_autopilot(
        account_id: str, change: AutopilotChange, who: Annotated[str, Depends(person)]
    ) -> AutopilotView:
        wanted = slug(account_id)
        svc = autopilot_service()
        try:
            if change.preset is not None:
                svc.apply_preset(wanted, change.preset, who, change.reason, utcnow())
            else:
                assert change.field is not None
                svc.set(wanted, change.field, change.value, who, change.reason, utcnow())
            return autopilot_view(svc, wanted)
        except UnknownAutopilotAccount:
            raise HTTPException(404, "unknown account") from None
        except AutopilotError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/admin/policy/dry-run", dependencies=authorized)
    def get_policy_dry_run(account: str | None = None) -> PolicyDryRun:
        """The gate over every eligible queued item; writes nothing (log #461)."""
        wanted = slug(account) if account is not None else None
        return dry_run(posting_of(ctx.deps()), settings.blueprints_dir, utcnow(), wanted)

    @app.post("/telegram/webhook")
    def telegram_webhook(
        body: Annotated[dict[str, Any], Body()],
        x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        sender = ctx.sender()
        if settings.telegram_webhook_secret is None or sender is None:
            raise HTTPException(503, "TELEGRAM_WEBHOOK_SECRET / TELEGRAM_BOT_TOKEN not configured")
        if not _same(
            x_telegram_bot_api_secret_token, settings.telegram_webhook_secret.get_secret_value()
        ):
            raise HTTPException(403, "bad secret token")
        try:
            handle_update(body, BotContext(settings, sender, ctx.deps()))
        except Exception as exc:
            # The update is already claimed, so Telegram's redelivery would be dropped anyway;
            # a 5xx would only make Telegram back off the whole webhook.
            # Telegram/httpx errors can carry the bot-token URL: no raw traceback for them.
            leaky = is_db_error(exc) or isinstance(exc, (httpx.HTTPError, TelegramError))
            log.warning("handling a Telegram update failed: %s", redact(exc), exc_info=not leaky)
        return {"ok": True}

    return app
