# Test fixtures

| File | What it is |
|---|---|
| `talking_head_10s.mp4` | 10 s of real speech, 480x854 portrait, h264/aac, ~530 KB. Used by tests that need an actual voice (ASR, caption look) and by the blur-fit reframe path. |
| `transcript_short.json` | Hand-made 10 s transcript with word times and sentence punctuation. Synthetic text, not a transcript of any real video. |
| `llm_valid.json` | Two valid clips for the 12-min transcript from `tests/builders.py::build_long_transcript`, with times slightly off sentence boundaries (to exercise snapping). |
| `llm_fenced.txt` | Valid JSON wrapped in prose and a ```json fence, with an extra key. |
| `llm_malformed.txt` | Truncated JSON. |
| `llm_invalid_schema.json` | Parses as JSON but fails validation (end < start, score > 1). |
| `llm_out_of_range.json` | Valid schema, but the clip ends after the transcript. |
| `llm_empty.json` | `{"clips": []}`. |
| `api_contract_2026-09-29.json` | Frozen JSON schemas of `JobView`, `PostingOverview` and `ChannelProgress` as the S3a dashboard was generated from them on 2026-09-29. `tests/test_api_contract.py` checks that responses only grow (no field or enum member removed, renamed or retyped). Never edit it. |

Synthetic video/audio is generated at test time by the `media` fixture in `tests/conftest.py` (ffmpeg `testsrc2` + `sine`); the talking-head clip is the only committed media file.

## Recreating the talking-head clip

```bash
ffmpeg -i <source.mp4> -t 10 -c:v libx264 -preset veryfast -crf 28 -c:a aac -b:a 96k \
  -movflags +faststart tests/fixtures/talking_head_10s.mp4
```
