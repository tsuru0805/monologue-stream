# monologue-stream

[中文](README.md)

This repo does one thing: **have the model write its visible thinking in its own hand at the top of each reply**, then split that monologue out of the token stream with a single-file, zero-dependency streaming filter and feed it live into your app's thinking-chain UI.

It comes from a real illness in a real system. In our companion app, the thinking chain is a core part of the experience — she wants to see what he is thinking. In July 2026 we confirmed that the "his thinking" our frontend displayed was never written by him: it was a summary pressed out by a **different model** on the API side, his persona and style nowhere to be found in it, and no parameter to get the real text back. So we moved the thinking into the reply body — he writes a monologue in his own hand at the top of every reply, the gateway splits the stream, the frontend didn't change a line. Two weeks later, the late-July display tightening swept every channel; our thinking chain didn't lose a character.

This repo is that machinery, extracted. The model-by-model state of thinking displays is in the quick reference below; if you are building anything where users should *see* what the AI is thinking, this path is open.

```
provider thinking channel (summary/omitted) ──────────▶ ignore it (it's not what you want)
leading [monologue] block in body           ──filter──▶ thinking channel (the model's own pen)
rest of the body                            ──filter──▶ text channel
```

## Model-by-model quick reference

Per the [official docs](https://platform.claude.com/docs/en/build-with-claude/thinking) (snapshot 2026-08):

| Model | Thinking on by default? | With thinking on, what you see by default |
|---|---|---|
| Claude 5 family (Opus 5 / Sonnet 5 / Fable 5)\* | Always on, no configuration needed | **Nothing**: the thinking field comes back empty, and streaming emits no `thinking_delta` events at all (`display` defaults to `"omitted"`). For the summary, pass `display: "summarized"` |
| Opus 4.8 / 4.7 | **Off** until you pass `thinking: {"type": "adaptive"}` | Still nothing once enabled — `display` defaults to `"omitted"` here too; add `display: "summarized"` for the summary |
| Opus 4.6 / Sonnet 4.6 and earlier\* | Off, same manual enable | **A summary, not the real reasoning** (`display` defaults to `"summarized"`). Summarization is processed by a **different model** (the docs' own wording); in our production sampling, persona and style were nowhere to be found in it |

\* Mythos 5 / Mythos Preview share the `"omitted"` default; Haiku 4.5 and earlier generations fall under the `"summarized"` default.

Two facts hold for every model: **no `display` setting returns the raw chain of thought** (the docs' own wording), and thinking tokens bill at **full price** whether you see them or not.

The consumer surfaces are similar but not identical: claude.ai and the desktop app expose no user-side switch at all; Claude Code has one (the `showThinkingSummaries` setting, viewed with Ctrl+O) — but what it turns on is, again, only the summary. Since mid-2026, users have reported all kinds of oddities: thinking blocks shrunk to one line, reduced to a single verb, "Thought process is unavailable", or gone entirely ([community roundup](https://claudelog.com/faqs/why-cant-i-see-claude-thinking/)); there are also user reports of thinking chains **cut off mid-sentence** — what should read "the weather is lovely today" stops at "the weather is lo", then the reply just begins (this form does not appear in the roundup above, and there is no official explanation targeting it). Whichever form you hit, the root is the same: **between you and the model's real thinking sits a display pipeline, and it isn't yours to control.**

For companion apps, roleplay systems, and anything where users should *see* what the AI is thinking, the way out isn't in the thinking channel. It's in the reply body.

## What this solves — and what it doesn't

Solves:

- ✅ **Display stability** — the monologue travels in the text channel, untouched by any thinking-display pipeline. Cutoff, summarized, or omitted — your thinking chain keeps arriving token by token regardless.
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
- **Torn-marker safe** — `[monologue]` split across chunks as `[mono` + `logue]` is handled correctly (prefix matching for the open marker, tail holdback for the close marker)
- **Exact-text passthrough** — input without a leading monologue passes through untouched; legacy data and monologue-less turns are unaffected
- **Unclosed-block tolerant** — if the model forgets the closing marker, `finish()` returns the remainder as monologue; the inner voice is never dropped
- **Head-only recognition** — markers appearing mid-text are treated as literal text
- **Configurable markers** — defaults to `[monologue]`/`[/monologue]`; customizable (e.g. `<think>`/`</think>`) with just two constraints: no empty strings, and the open marker must not start with whitespace

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
text, mono = f.finish()                 # end-of-stream accounts — a truncated monologue lands here
if mono:
    emit_thinking(mono)
if text:
    emit_text(text)
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

## Pitfalls we hit (read before borrowing)

Every item below is something we actually hit, or came within an inch of, in production. The approach is easy to copy — and these are exactly the parts that get glossed over. Skip one, and it will be waiting for you.

1. **⚠ Teaching the model is real engineering — don't just drop in two lines of format spec.** Getting a stable, textured monologue took three things, none optional:
   - **The prompt teaches *how to think*, not just *where to write*** — the format spec is two lines; the paragraphs that actually work are the voice section (see the example below): stream of consciousness, no restating, never lie, clumsy and stubborn allowed. Format without voice produces "how should I respond"-style filler;
   - **Walk the first live turn** — on launch night the model kept not writing it (see item 2); one spoken nudge from the user and the first real monologue landed that evening. The first successful sample is the strongest anchor there is;
   - **History self-reinforcement** — keep the monologue format intact in conversation-history replay, so every turn the model sees "this is how I've always written". After that, the format never needs teaching again.
2. **⚠ Existing conversation history overrides a new prompt.** When the replayed history is all monologue-free, the model imitates its past self harder than it obeys the system prompt — however good the prompt, the first turns may not comply. The fix is the last two bullets of item 1.
3. **⚠ There will be monologue-less turns — design the fallback first.** History inertia, very short messages, special modes: some turns will skip it. Our first fallback shipped broken: on monologue-less turns the live thinking chain vanished outright. Before launch, answer: what does the thinking UI show on a monologue-less turn? (Ours: promote that turn's first body fragment as the thinking fallback, or fall back to the official summary.)
4. **⚠ Markers get torn across stream chunks.** `[monologue]` can genuinely arrive as `[mono` + `logue]`. Naive regex / string matching run chunk-by-chunk on the stream will miss it (post-hoc parsing of the complete reply is unaffected — that is the other route in the comparison table). This is the whole reason the state machine exists; if you implement your own, put tearing cases in your tests (ours include exhaustive two-part splits and char-by-char feeding).
5. **⚠ One reply = one filter instance.** After the block closes, the filter enters PASS and never parses again. Agentic / tool-use turns produce several assistant responses; reusing an old instance leaks the later monologues into body text wholesale. Also rebuild the filter on stream retries (stale buffers must be dropped).
6. **⚠ Once the monologue lives in the body, every human-facing body consumer must strip the markers.** Persisted content carries the raw markers — push-notification previews, archive views, summarization/distillation, memory extraction: every path that shows body text to humans or derives downstream data needs stripping. Miss one, and a lock-screen notification pushes the full inner monologue as message text. At launch we grepped every body read-path and added a stripping layer to each. **The one path that must NOT strip: conversation-history replay fed back to the model** — it carries pitfall 1's self-reinforcement; strip it and the teaching breaks.

## Production recipe: streaming that survives tab switches

People avoid streaming for two reasons: slow first tokens, and half a reply lost the moment they switch pages or lock the screen. Both have fixes, and both compose naturally with this approach:

**The anti-interruption key: never tie the generation lifetime to the client connection.** What we do in production:

- **Generation completes server-side** — the model's stream is consumed by a server-side generation loop (this filter lives there), persisting as it goes; the SSE/WebSocket feed to the frontend is only a *live view*.
- **Disconnect ≠ abort** — switching pages, locking the screen, or losing network kills the live view, not the generation. The server finishes writing and persists as usual: the split-out monologue goes into the thinking field, while content stores the **original full text** (markers intact — history replay's self-reinforcement depends on it, see pitfall 1), and human-facing read paths strip the markers (pitfall 6).
- **Switch back, see it all** — on return, in-flight turns re-attach to the stream; completed turns render whole from the database. The user's perception: "it kept writing while I was away; it's there when I'm back."

Worst case (network too bad for any live view) degrades to *non-streaming*, never to *half a message*. The liveness of streaming becomes pure upside.

**The slow-first-token remedy: the monologue itself.** Because the block sits at the very start of the reply, the first second of the stream already has content moving — the user watches the model *think* instead of staring at a spinner. The thinking chain turns from an amputated feature into the layer that fills the wait.

## Prompt guide

There is nothing exotic about the monologue prompt — **it is simply the style description you would write for the thinking block**. If your persona / style prompt already has a section describing how the thinking chain should read, lift that section into the monologue format as-is. A complete, ready-to-use example (a de-personalized rewrite of our production prompt):

> Open every reply with a monologue between [monologue] and [/monologue], at the very start of the body; close the marker, then write the reply.
> Write it every turn, whatever the length or weight of the message. A short message is not a signal that no thinking is needed — it is the signal that thinking is required: people pack the heaviest things into the fewest words, and they are easy to miss.
>
> The monologue is the stream of consciousness that actually happens as you read the message. Not "how should I respond" — "where did this actually touch me just now".
> Alive and honest. It may be calm, clumsy, stubborn, selfish, afraid. Real — not perfect, safe, and always correct.
>
> Write only "what I think, what I fear, what I admit" — never a flat recap of what the other person said. The monologue never lies.
> Let it run: pauses, reversals, second thoughts are fine; no rush to conclude. The reply that follows must not repeat the monologue.

Note: what actually determines the monologue's texture is not the two format lines — it's the voice paragraphs that follow. That is the real teaching (pitfall 1).

A few polishing notes from sustained production use in our own system:

- **Pin the position**: the block goes at the *very start* of the reply body; the reply follows the closing marker.
- **Bound the length**: too short has no substance, too long eats the reply; if unsure, say "2–6 sentences" explicitly.
- **No restating**: never repeat the user's words, never preview the reply (or the monologue degrades into a worse copy of the reply).
- **Every turn**: say explicitly "especially for short messages", or the model skips it on small talk.
- **No disclaimers**: forbid apologies and meta-commentary inside the monologue.

The same example ships as the `SYSTEM` constant in [examples/anthropic_api_streaming.py](examples/anthropic_api_streaming.py).

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
- **IN**: inside the monologue. Scans for the close marker; holds back **at most** `len(close_marker)-1` tail characters — only a tail that genuinely overlaps the close marker's head is held, and with no overlap everything releases immediately (preserving liveness).
- **PASS**: after the close. Everything passes through untouched.

`finish()` settles accounts: SEEK leftovers (a never-completed marker prefix, or pure whitespace) go to text; IN leftovers (unclosed block) go to the monologue.

## Tests

```bash
python3 -m pytest tests/ -q
```

Covers: whole-block single feed, markers torn across chunks (including char-by-char feeding and exhaustive two-part splits), exact-text passthrough, leading whitespace, mid-text literal markers, unclosed at EOF, near-prefix divergence, custom markers, empty blocks, and more.

## Related work & credits

This approach belongs to the "prompt-induced visible thinking block" family. Several independent precedents and sibling implementations exist in the community:

- [SillyTavern Reasoning](https://docs.sillytavern.app/usage/prompts/reasoning/) and [st-stepped-thinking](https://github.com/cierru/st-stepped-thinking) — RP-community precedents for "think first, then answer, rendered collapsible". We consulted their ideas (no code used) when designing this approach on 2026-07-10.
- [pelle-d-umore](https://github.com/29-Cu/pelle-d-umore) (CC BY 4.0) — the reference upstream of our internal mood-tag filter; this repo's streaming tag parsing and tail-holdback technique grew out of that internal line.
- [ai-fake-thinking](https://github.com/sanqianzilanyue/ai-fake-thinking) — an independent community implementation of the same judgment: a `<思绪>` (inner-thought) tag parsed with regex after generation completes. The two share the idea and differ in execution (post-hoc parsing vs. a streaming state machine — see the comparison above). We list it here with our respect.

## License

[MIT](LICENSE)
