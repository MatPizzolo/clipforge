# Evals

> **Planned (ROADMAP Phase 5):** `evals/` and `clipforge eval` aren't built yet. This page is the design.

Prompt and model changes must not make highlight selection worse. The eval set catches regressions before they reach real output.

## Eval set

`evals/v1/` holds 20–30 permitted source videos (podcasts, interviews, talks, solo commentary, several languages), each with:

```
evals/v1/<id>/
  transcript.json      # cached, so evals never re-transcribe
  gold.json            # human-marked good segments: [{start, end, quality: 1-3}]
```

Annotate by watching at 1.5x and marking every segment you would post; expect 5–15 per hour of content.

## Metrics

- **Precision@n:** share of the top-n predicted clips overlapping a gold segment (IoU ≥ 0.5).
- **Recall:** share of quality-3 gold segments found in the top-n.
- **Boundary error:** mean absolute start/end difference (s) vs. matched gold segments.
- **Standalone rate:** LLM-as-judge check that the clip makes sense without context (spot-check by hand).
- **Cost and latency** per source hour.

## Running

```bash
uv run clipforge eval --set evals/v1 --prompt highlights_v2 --model claude-haiku-4-5
```

Results go to `evals/results/<timestamp>.json` and to the experiment tracker (Phase 5).

## Ship rule

A new prompt version ships only if precision@5 doesn't drop and cost per source hour rises less than 20%, unless the PR explains why.

## Production feedback

👍/👎/re-cut ratings and, later, platform retention are logged per clip with its features, prompt version and model. Periodically promote well-rated production clips into the next eval set version.
