"""Turn ranked highlight candidates into this job's clip specs."""

from __future__ import annotations

from clipforge.models import ClipOptions, ClipSpec, HighlightsResult, SourceMedia

AUTO_MAX_CLIPS = 30  # cap for automatic mode, so a 3 h source doesn't make 60 clips


def select_clips(
    result: HighlightsResult, source: SourceMedia, options: ClipOptions
) -> list[ClipSpec]:
    """The selected candidates as ClipSpecs; `clip_01` is the best.

    With `options.n` set: the top n, whatever their score. With `n` None (automatic): every
    candidate scoring at least `options.min_score`, at most AUTO_MAX_CLIPS.

    `result.candidates` is already ranked and length-filtered by the highlights stage, which
    is cached without `n` (ADR-8). This only skips candidates ending after the source and
    assigns ids.
    """
    limit = options.n if options.n is not None else AUTO_MAX_CLIPS
    specs: list[ClipSpec] = []
    for candidate in result.candidates:
        if len(specs) == limit:
            break
        if options.n is None and candidate.score < options.min_score:
            break  # candidates are ranked by score, so none of the rest qualify
        if candidate.end > source.duration_s:
            continue
        rank = len(specs) + 1
        specs.append(
            ClipSpec(
                clip_id=f"clip_{rank:02d}",
                rank=rank,
                source=source,
                start=candidate.start,
                end=candidate.end,
                candidate=candidate,
                options=options,
            )
        )
    return specs
