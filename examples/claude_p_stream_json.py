"""Claude Code CLI integration via `claude -p` stream-json.

If your backend drives Claude through the Claude Code CLI in print mode
(`claude -p`), you never touch the raw API stream -- but with
`--include-partial-messages` you still receive text deltas, as JSON lines:
each line of type "stream_event" wraps a raw Anthropic streaming event, and
text deltas arrive as content_block_delta / text_delta. Feed those through
the filter in order.

(The Python Agent SDK yields typed StreamEvent objects instead of JSON
lines; the wiring principle is the same -- feed text deltas in order, one
filter instance per assistant response.)

Requires: the `claude` CLI on PATH, logged in.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monologue_filter import MonologueFilter

DIM, RESET = "\033[2m", "\033[0m"

SYSTEM_APPEND = (
    "Begin every reply with a 2-5 sentence first-person inner monologue "
    "wrapped as [monologue]...[/monologue] at the very start, then the reply."
)


def main() -> None:
    proc = subprocess.Popen(
        [
            "claude", "-p", "--verbose",
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--append-system-prompt", SYSTEM_APPEND,
            "Hey, how was your day?",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None

    f = MonologueFilter()
    for line in proc.stdout:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") != "stream_event":
            continue
        inner = ev.get("event", {})
        if inner.get("type") != "content_block_delta":
            continue
        delta = inner.get("delta", {})
        if delta.get("type") != "text_delta":
            continue

        text, mono, closed = f.feed(delta.get("text", ""))
        if mono:
            print(f"{DIM}{mono}{RESET}", end="", flush=True)
        if closed:
            print()
        if text:
            print(text, end="", flush=True)

    text, mono = f.finish()
    if mono:
        print(f"{DIM}{mono}{RESET}", end="")
    if text:
        print(text, end="")
    print()
    if proc.wait() != 0:
        print(f"claude exited with status {proc.returncode}", file=sys.stderr)


if __name__ == "__main__":
    main()
