# Card 012: X4 — visuals and music spike

Status: proposed
Stream: X4 · Branch: `x4/visuals-music` · Worktree: `../clipForge-x4` (created with `scripts/worktree.sh x4/visuals-music`)
Decision-log range: #470–#479 (append only, in this range)
Model: most capable
Depends on: nothing. Runs alongside cards 010, 011 and 013
Cost cap: $15 of Modal GPU (stop and ask before exceeding it)

## Context
The first AI account (wave 2: untold.archive and historias.ocultas, story producer S6) needs stills, short b-roll and music beds. S5 builds the media servers for them, and it needs this spike's answers first: which models, on which GPU, at what cost per unit, and whether the quality is good enough. 06's X4 card has the question and candidates; X1 (voice, done) is the model for how a spike runs and reports (`docs/studio/spikes/x1-voice.md`).

Since 06 was written, S4 shipped the Timeline renderer (card 006; ADR-31, ADR-47): stills with Ken Burns, b-roll segments, and music ducked under narration all render in one encode. So this spike can also make one end-to-end sample, a short Timeline from its own outputs, to judge them in context.

Rules from ADR-30: every model's license must be commercially usable, and many popular ones aren't (FLUX.1-dev, Qwen-Image 2.1, MusicGen and others are non-commercial). Check each candidate's license and pin its revision before generating anything with it.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. 06's X4 card and prompt C (spikes), `docs/studio/03-tools-and-models.md` (candidates, GPU prices), `docs/studio/spikes/x1-voice.md` (the report shape)
3. ADR-30, ADR-31, ADR-47; `stages/timeline.py`, `stages/render_graph.py` (how a Timeline is built)
4. `docs/studio/07` (the story accounts' visual style), 02 §4 (media servers)

## Scope
- May edit, as `scripts/scopes.toml` allows for `x4/`: `docs/studio/spikes/x4-visuals-music.md` (new), `docs/studio/03-tools-and-models.md` (measured numbers), `docs/studio/04-roadmap.md` (the X4 line).
- Probe code only in `scratch/x4/` (ignored by git). Deployed spike apps are named `clipforge-x4*`; never touch the `clipforge` app. Weights go on the `clipforge-models` Volume under `x4/`.
- Must not edit: `src/`, `tests/`, other docs.

## Actions
1. **Licenses first:** for each candidate (Z-Image-Turbo, Qwen-Image-2512, Wan2.2 TI2V-5B and A14B with lightx2v, ACE-Step 1.5), record the license, whether commercial use is allowed, and the pinned revision. Drop any that fail; tell the owner.
2. **Stills:** Z-Image-Turbo on L4 (FP8) vs L40S; Qwen-Image-2512 for images with text. 1080x1920 (or the size the renderer scales from), 10 prompts in the story accounts' style. Measure seconds and dollars per image, cold start.
3. **B-roll:** Wan2.2 TI2V-5B vs A14B with lightx2v, 5 s clips. Measure seconds and dollars per clip, cold start, and whether 24 fps output needs interpolation.
4. **Music:** ACE-Step 1.5, 60 s beds in 3–4 moods. Measure seconds and dollars per bed.
5. **One end-to-end sample:** a 30–60 s Timeline from the spike's outputs (stills with Ken Burns, one b-roll, a music bed ducked under a narration line from X1's TTS or a placeholder) rendered with S4's renderer, locally or in a spike app. It shows the parts in context.
6. **Blind samples for the owner:** the best and second-best per category, unlabeled. Report, and wait for the owner's ratings.
7. **After the verdict:** write the spike report (the X1 shape: question, candidates, licenses, numbers, ratings, recommendation, what S5 should build), update 03's numbers and the X4 line in 04. Stop every `clipforge-x4*` app; keep or delete the `x4/` weights as the owner chooses.

## Checkpoints
- A: after actions 1–6 (the numbers and the blind samples). Report and stop for the owner's ratings.
- B: after action 7. Suggested commit: `012: x4: visuals and music spike report`

## Done when
- The report has, per category: license, $ per unit, seconds per unit, cold start, the owner's blind rating, and a recommendation for S5.
- Every spike app is stopped, and spend is under $15.
- `scripts/check.sh --docs --scope` is green.

## Owner steps
- Before: `scripts/worktree.sh x4/visuals-music`, open a session in `../clipForge-x4`, paste `Run card docs/cards/012-x4-visuals-music.md`. The session asks before each Modal run (`modal run`/`deploy` of spike apps only).
- At A: rate the blind samples.
- At B: commit, `git push -u origin x4/visuals-music`, open the PR, squash-merge when green.

## Hand-off
Write `docs/reports/012-x4-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at each checkpoint. Don't commit: the owner does.
