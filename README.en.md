# monologue-stream

[中文](README.md)

Put the "thinking process" back in the model's own hands: instruct the model to open every reply with a self-authored monologue, then stream-split it into your app's "thinking" UI channel with a zero-dependency filter.

```
provider thinking channel (summary/omitted) ──────────▶ ignore it (it's not what you want)
leading [monologue] block in body           ──filter──▶ thinking channel (the model's own pen)
rest of the body                            ──filter──▶ text channel
```

## What happened to thinking displays lately

Since late July 2026, the same phenomenon hit every channel (claude.ai, Claude Code, direct API): thinking blocks went from line-by-line reasoning to a one-sentence summary, a single verb, "Thought process is unavailable", or nothing at all. Many concluded the model "got dumber" or "stopped thinking". Unpacked, there are three layers:

1. **It's a display policy, not vanished reasoning.** Since the Claude 4 generation, extended thinking displays a **summary** by default; newer adaptive-thinking models further default to summarized or **omitted** display. The reasoning still happens and is still billed at **full** thinking-token count — you just don't see it ([official docs](https://platform.claude.com/docs/en/build-with-claude/extended-thinking), [community roundup](https://claudelog.com/faqs/why-cant-i-see-claude-thinking/)).
2. **The summary is not the model's voice.** It is produced by a **different model** that ignores your system prompt, persona, and style — even when displayed, it is a third party's paraphrase, not your character's inner voice. The more the model thinks, the more the paraphrase distorts.
3. **There is no client-side switch.** No display mode returns raw chain-of-thought, and nothing lets you turn the summarization off.

For companion apps, roleplay systems, and anything where users should *see* what the AI is thinking, these three layers stack up to one fact: the thinking display **is not under your control**. So instead of fighting the display layer, switch channels — **have the model write its visible thinking in its own hand, in the reply body**: the body passes through no summarization or rewriting layer, and always obeys your prompts.

## What this solves — and what it doesn't

Solves:

- ✅ **Display stability** — the monologue travels in the text channel, untouched by any thinking-display policy. However the provider tightens the display, your thinking chain keeps arriving token by token. We have run this in our private companion system since 2026-07-10, sat through the late-July tightening, zero impact.
- ✅ **The voice comes home** — the thinking chain is written by the *same* model, in character, under *your* system prompt and style.
- ✅ **Live streaming** — the monologue reaches the thinking channel as it is generated, not parsed after the fact.
- ✅ **A designable experience** — length, tone, and format of the thinking are all governed by your prompt.

Doesn't solve (honest boundaries):

- ❌ **It cannot recover the hidden raw CoT** — the monologue is visible introspection the model writes in-context for humans to read, not the internal reasoning transcript.
- ❌ **It does not change actual reasoning depth** — how hard the model thinks is set by thinking budget / effort, independent of display; the "the model really did get dumber" class of complaints is out of scope here.
- ❌ **It cannot bypass hard limits** — `max_tokens` cutoffs and dropped streams still happen (the filter only guarantees that monologue already written is never lost on truncation; see Features).

For companion and RP use, an authored inner voice is usually much closer to what you actually want than a third party's paraphrase of the reasoning — just be clear about which one you are getting.

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

## Production recipe: streaming that survives tab switches

People avoid streaming for two reasons: slow first tokens, and half a reply lost the moment they switch pages or lock the screen. Both have fixes, and both compose naturally with this approach:

**The anti-interruption key: never tie the generation lifetime to the client connection.** What we do in production:

- **Generation completes server-side** — the model's stream is consumed by a server-side generation loop (this filter lives there), persisting as it goes; the SSE/WebSocket feed to the frontend is only a *live view*.
- **Disconnect ≠ abort** — switching pages, locking the screen, or losing network kills the live view, not the generation. The server finishes writing and persists as usual (monologue into the thinking field, body into the content field — the split itself is persisted).
- **Switch back, see it all** — on return, in-flight turns re-attach to the stream; completed turns render whole from the database. The user's perception: "it kept writing while I was away; it's there when I'm back."

Worst case (network too bad for any live view) degrades to *non-streaming*, never to *half a message*. The liveness of streaming becomes pure upside.

**The slow-first-token remedy: the monologue itself.** Because the block sits at the very start of the reply, the first second of the stream already has content moving — the user watches the model *think* instead of staring at a spinner. The thinking chain turns from an amputated feature into the layer that fills the wait.

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
