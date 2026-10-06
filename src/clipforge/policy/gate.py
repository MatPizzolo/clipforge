"""The policy gate v1 (ADR-29, S2 spec §5.1): pure checks on one item and its per-platform copy.
Any violation sends the item to review; the gate never edits anything. In S2a it only logs and
stamps (`GATE_ENFORCE` off, log #461). The banned-claims check comes with the Judge in S6."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from clipforge.models import Account, ContentItem, GateResult, Platform, PostCopy, Source, Violation
from clipforge.posting.queue import SAME_MOMENT_IOU, iou, video
from clipforge.sources import hold_reason

AI_KINDS = frozenset({"generated", "music_generated"})


def _has_ad(c: PostCopy) -> bool:
    return "ad" in (t.lower().lstrip("#") for t in c.hashtags) or "#ad" in c.text.lower().split()


def gate(
    item: ContentItem,
    account: Account,
    source: Source | None,
    copy: dict[Platform, PostCopy],
    others: Iterable[ContentItem],
    *,
    require_credit: bool,
    platforms: list[Platform],
    now: datetime,
) -> GateResult:
    """`others`: planned and posted items that share the item's video, any account (read by the
    caller). `require_credit`: the blueprint's compliance profile."""
    out: list[Violation] = []
    if any(a.kind in AI_KINDS for a in item.assets) and not item.ai_disclosure:
        out.append(Violation(code="missing_ai_label", message="AI-made media without the AI label"))
    needs_credit = require_credit or (source is not None and source.kind == "channel")
    for p in platforms:
        c = copy.get(p)
        if c is None:
            continue
        if item.sponsored and not _has_ad(c):
            out.append(Violation(code="missing_ad", platform=p, message="sponsored without #ad"))
        if needs_credit and source is not None and source.credit_name not in c.text:
            out.append(
                Violation(
                    code="missing_credit",
                    platform=p,
                    message=f"the credit {source.credit_name!r} is missing",
                )
            )
    for a in item.assets:
        if a.kind == "source_video":
            # checked against the source's current permission, so Dict items stamped
            # `unrecorded` pass once their source records one (spec §5.1)
            if source is None:
                out.append(
                    Violation(
                        code="license_unrecorded",
                        message="source video without a recorded permission",
                    )
                )
        elif not a.license or a.license == "unrecorded":
            out.append(
                Violation(code="license_unrecorded", message=f"{a.kind} asset without a license")
            )
    if any(
        o.account_id != item.account_id
        and video(o) == video(item)
        and iou(o, item) > SAME_MOMENT_IOU
        for o in others
    ):
        out.append(
            Violation(
                code="cross_account_duplicate",
                message="the same moment is planned or posted on another account",
            )
        )
    if (reason := hold_reason(source, platforms, now)) is not None:
        out.append(Violation(code="source_held", message=reason))
    return GateResult(violations=out)


def codes(result: GateResult) -> list[str]:
    """The violation codes, each once, in order (for log lines and the dry run)."""
    return list(dict.fromkeys(v.code for v in result.violations))
