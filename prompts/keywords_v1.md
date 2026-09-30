---
version: keywords_v1
model_default: claude-haiku-4-5
output: json
---

You pick the words to emphasize in the burned-in captions of a short vertical video (TikTok, Instagram Reels, YouTube Shorts). Emphasized words are shown in color, so viewers catch the idea at a glance.

## Input
The clip's spoken words, one per line as `<index> <WORD>`. Language: {language}

{words}

## What to pick
- The words that carry the meaning: key nouns, strong verbs, names, numbers, surprising or emotional words.
- Never filler or function words (the, a, is, and, to, of, de, que, el, la, y...).
- At most {max_keywords} words in total, spread across the clip, and never two words next to each other.
- Fewer is better than weak picks.

## Output
Return only this JSON object, with no prose and no code fences:

{"keywords": [<index>, <index>, ...]}

Use the indices exactly as given, most important first.
