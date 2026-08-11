# monologue-stream

[中文](README.md)

Put the "thinking process" back in the model's own hands: instruct the model to open every reply with a self-authored monologue, then stream-split it into your app's "thinking" UI channel with a zero-dependency filter.

```
provider thinking channel (summary/omitted) ──────────▶ ignore it (it's not what you want)
leading [monologue] block in body           ──filter──▶ thinking channel (the model's own pen)
rest of the body                            ──filter──▶ text channel
```

## Why

If you build companion apps, roleplay systems, or anything where users should *see* what the AI is thinking, you have probably hit these walls:

- Since the Claude 4 generation, extended thinking is displayed as a **summary** by default — produced by a **different model** that ignores your system prompt, persona, and style ([official docs](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)).
- Since late July 2026, adaptive-thinking models tightened the display further: thinking blocks collapse into one-line summaries, a single verb, or "Thought process is unavailable" — and some newer models default to **omitting** the thinking display entirely (see the r/ClaudeAI wave, [background](https://claudelog.com/faqs/why-cant-i-see-claude-thinking/)).
- You pay for the **full** thinking tokens; you see a compressed digest, or nothing. The more the model thinks, the more the display distorts.

These are display-layer policies you cannot turn off from the client. Instead of fighting the display layer, switch channels: **have the model write its visible thinking in the reply body** — the body passes through no summarization or rewriting layer; every character you receive is the model's own, under your prompts. (Hard limits like `max_tokens` still apply, of course — which is why the filter tolerates unclosed, truncated streams; see Features.)

We have run this in our private companion system since 2026-07-10, sat through the late-July display tightening, and our thinking display was untouched.

## An honest note

The monologue is **not** recovered chain-of-thought. It is visible introspection the model writes in-context, in-character, with its own pen — not the raw internal reasoning. But it comes from the *same* model, under *your* system prompt and style, whereas the official thinking summary comes from a *different* model that ignores all of it. For companion and RP use, an authored inner voice is usually much closer to what you actually want than a third party's paraphrase of the reasoning.

## Features

- **Single file, zero dependencies** — copy `monologue_filter.py` into your project
- **Streaming** — the monologue reaches your thinking channel token by token, live; no post-hoc parsing
- **Torn-marker safe** — `[monologue]` split across chunks as `[mono` + `logue]` is handled correctly (prefix matching + tail holdback)
- **Exact-text passthrough** — input without a leading monologue passes through untouched; legacy data and monologue-less turns are unaffected
- **Unclosed-block tolerant** — if the model forgets the closing marker, `finish()` returns the remainder as monologue; the inner voice is never dropped
- **Head-only recognition** — markers appearing mid-text are treated as literal text
- **Configurable markers** — defaults to `[monologue]`/`[/monologue]`; use any strings you like (e.g. `<think>`/`</think>`)

## Quick start

```python
from monologue_filter import MonologueFilter

f = MonologueFilter()
for delta in your_text_stream:          # streamed text deltas from any source
    text, mono, closed = f.feed(delta)
    if mono:
        emit_thinking(mono)             # → your thinking UI channel
    if text:
        emit_text(text)                 # → your text channel
text, mono = f.finish()                 # settle accounts at end of stream
```

Add a system prompt (see [Prompt guide](#prompt-guide)) and you are done.

## Three ways to integrate

### 1. Direct API (streaming)

Full filter integration: see [examples/anthropic_api_streaming.py](examples/anthropic_api_streaming.py). Keep or ignore the API's thinking events, if any (they carry the summary, or nothing); run text deltas through the filter and dispatch. If your frontend already has a thinking-chain component, the event contract stays the same — only the content changes.

### 2. Claude Code CLI (`claude -p` stream-json) / Agent SDK

If your backend drives Claude through a Claude Code backend, the same filter applies. In CLI print mode with `--include-partial-messages`, text deltas arrive as JSON lines — feed them through in order, see [examples/claude_p_stream_json.py](examples/claude_p_stream_json.py). The Python Agent SDK yields typed `StreamEvent` objects rather than JSON lines, but the wiring principle is identical: feed the text deltas through in order. Mind the lifetime: **one filter instance covers one reply** — in agentic loops that produce several assistant responses per turn, create a fresh instance per response.

### 3. Interactive Claude Code (no code at all)

In interactive Claude Code you don't control the rendering layer — but you don't need this filter either: the reply body renders in full, so a monologue written in the body is naturally immune to thinking-display policies. Add to your `CLAUDE.md` (or an output style):

```markdown
Open every reply with a blockquote (>) of 2-5 first-person sentences of your
actual thinking — what you noticed, why this angle, what you're unsure about —
then start the reply proper.
```

The blockquote/italics play the role of the collapsed thinking chain.

## Prompt guide

What we learned from running this in production in our own system:

- **Pin the position**: the block goes at the *very start* of the reply body; the reply follows the closing marker.
- **Bound the length**: 2–6 sentences. Shorter has no substance; longer eats the reply.
- **First person, present tense**: what the model is *actually* thinking right now — what it noticed, what it hesitates over, why this angle.
- **No restating**: never repeat the user's words, never preview the reply (or the monologue degrades into a worse copy of the reply).
- **Every turn**: say explicitly "especially for short messages", or the model skips it on small talk.
- **No disclaimers**: forbid apologies and meta-commentary inside the monologue.

A sample system prompt is at the top of [examples/anthropic_api_streaming.py](examples/anthropic_api_streaming.py).

## Compared to post-hoc parsing

| | Post-hoc regex parsing | Streaming state machine (this repo) |
|---|---|---|
| When thinking appears | after the full reply is generated | live, token by token |
| Truncated stream (unclosed block) | commonly the whole reply is discarded | remainder returned as monologue, nothing lost |
| Integration requirement | needs the complete reply text | any sequence of deltas |
| Markers mid-text | needs extra guards | head-only by design, naturally immune |

## Engineering details

The filter is a three-state machine:

- **SEEK**: at stream start. Tolerates leading whitespace; checks character by character whether the buffer is still a prefix of the open marker — on divergence, the whole buffer is released as literal text and parsing never resumes (which is why mid-text markers are naturally literal).
- **IN**: inside the monologue. Scans for the close marker; holds back up to `len(close_marker)-1` suspicious tail characters so a marker torn across chunks is never mis-released.
- **PASS**: after the close. Everything passes through untouched.

`finish()` settles accounts: SEEK leftovers (a never-completed marker prefix, or pure whitespace) go to text; IN leftovers (unclosed block) go to the monologue.

## Tests

```bash
python3 -m pytest tests/ -q
```

Covers: whole-block single feed, markers torn across chunks (including char-by-char feeding and exhaustive two-part splits), byte-identical passthrough, leading whitespace, mid-text literal markers, unclosed at EOF, near-prefix divergence, custom markers, empty blocks, and more.

## Related work & credits

This approach belongs to the "prompt-induced visible thinking block" family. Several independent precedents and sibling implementations exist in the community:

- [SillyTavern Reasoning](https://docs.sillytavern.app/usage/prompts/reasoning/) and [st-stepped-thinking](https://github.com/cierru/st-stepped-thinking) — RP-community precedents for "think first, then answer, rendered collapsible". We consulted their ideas (no code used) when designing this approach on 2026-07-10.
- [pelle-d-umore](https://github.com/29-Cu/pelle-d-umore) (CC BY 4.0) — the engineering lineage of the tail-holdback pattern used in our streaming tag parsing (via the mood-tag filter in our internal system).
- [ai-fake-thinking](https://github.com/sanqianzilanyue/ai-fake-thinking) — an independent community implementation of the same judgment: a `<思绪>` (inner-thought) tag parsed with regex after generation completes. The two share the idea and differ in execution (post-hoc parsing vs. a streaming state machine — see the comparison above). We list it here with our respect.

## License

[MIT](LICENSE)
