"""Direct Anthropic API integration: route the monologue into a thinking channel.

Requires: pip install anthropic  (and ANTHROPIC_API_KEY in the environment)

The monologue prints dimmed (like a thinking trace); the reply prints normally.
In a real app you would emit the two channels as separate UI events instead.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic

from monologue_filter import MonologueFilter

SYSTEM = """\
Open every reply with a monologue between [monologue] and [/monologue], at
the very start of the body; close the marker, then write the reply.
Write it every turn, whatever the length or weight of the message. A short
message is not a signal that no thinking is needed -- it is the signal that
thinking is required: people pack the heaviest things into the fewest words,
and they are easy to miss.

The monologue is the stream of consciousness that actually happens as you
read the message. Not "how should I respond" -- "where did this actually
touch me just now". Alive and honest. It may be calm, clumsy, stubborn,
selfish, afraid. Real -- not perfect, safe, and always correct.

Write only "what I think, what I fear, what I admit" -- never a flat recap
of what the other person said. The monologue never lies.
Let it run: pauses, reversals, second thoughts are fine; no rush to
conclude. The reply that follows must not repeat the monologue.
"""

DIM, RESET = "\033[2m", "\033[0m"


def main() -> None:
    client = anthropic.Anthropic()
    f = MonologueFilter()

    # Note: thinking tokens count toward max_tokens on adaptive-thinking
    # models, so leave generous headroom for both thinking and the reply.
    with client.messages.stream(
        model="claude-sonnet-5",
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": "Hey, how was your day?"}],
    ) as stream:
        for delta in stream.text_stream:
            text, mono, closed = f.feed(delta)
            if mono:
                print(f"{DIM}{mono}{RESET}", end="", flush=True)
            if closed:
                print()  # blank line between thinking and reply
            if text:
                print(text, end="", flush=True)

    text, mono = f.finish()
    if mono:
        print(f"{DIM}{mono}{RESET}", end="")
    if text:
        print(text, end="")
    print()


if __name__ == "__main__":
    main()
