"""The seed library (hooks spec §4.1, ruling R3): five patterns and a control per clips account,
approved at equal weight by approving the spec. `clipforge hooks seed` writes them once."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import Connection

from clipforge.hooks.library import HookLibrary, SqlHookFreezer
from clipforge.models import HookPatternData


def _clips(
    name: str, structure: str, en: str | None = None, es: str | None = None
) -> HookPatternData:
    examples = {} if en is None or es is None else {"en": en, "es": es}
    return HookPatternData(name=name, structure=structure, examples=examples, fits=["clips"],
                           max_words=8)  # fmt: skip


# (control, body): the control ships the highlights title unchanged and is the baseline
CLIPS_SEEDS: list[tuple[bool, HookPatternData]] = [
    (True, _clips("Highlight title", "Ship the clip's own title unchanged")),
    (False, _clips("Number + stakes",
                   "Lead with a specific number from the clip and what it cost or won. Only"
                   " numbers and claims said in the clip; no promises.",
                   "$40K GONE IN ONE WEEK", "40 MIL PERDIDOS EN UNA SEMANA")),
    (False, _clips("Open question", "A question the clip answers, without giving the answer.",
                   "WHY DID HE WALK AWAY?", "¿POR QUÉ LO DEJÓ TODO?")),
    (False, _clips("Bold claim",
                   "The speaker's strongest claim, stated flatly. Only claims said in the clip;"
                   " no promises.",
                   "COLLEGE IS A SCAM", "LA UNIVERSIDAD ES UNA ESTAFA")),
    (False, _clips("Contrarian", "Name the common belief, then flip it.",
                   "EVERYONE SAYS SAVE. DON'T.", "TODOS DICEN AHORRA. NO.")),
    (False, _clips("The moment when",
                   "The turning point as a scene: \"the day…\", \"the moment…\".",
                   "THE DAY I GOT FIRED", "EL DÍA QUE ME DESPIDIERON")),
]  # fmt: skip


def seed(
    library: HookLibrary,
    account_ids: list[str],
    now: datetime,
    *,
    running: Callable[[str], list[int]] = lambda account_id: [],
    freezer: SqlHookFreezer | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Patterns written per account; an account with any pattern gets 0 (idempotent). For an
    account in running experiments (`running`, S3c's read once it is on main), the freezes are
    opened in the same transaction, so it never rotates unfrozen (spec §4.4)."""
    written: dict[str, int] = {}
    for account_id in account_ids:
        if dry_run:
            written[account_id] = 0 if library.patterns(account_id) else len(CLIPS_SEEDS)
            continue
        experiments = running(account_id)
        after = _freezes(freezer or SqlHookFreezer(library), account_id, experiments)
        written[account_id] = library.seed_patterns(
            account_id, CLIPS_SEEDS, now, after=after if experiments else None
        )
    return written


def _freezes(
    freezer: SqlHookFreezer, account_id: str, experiments: list[int]
) -> Callable[[Connection], None]:
    def run(conn: Connection) -> None:
        for experiment_id in experiments:
            freezer.freeze(conn, account_id, experiment_id)

    return run
