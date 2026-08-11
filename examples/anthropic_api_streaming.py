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
Begin every reply with a short inner monologue: 2-5 sentences, first person,
what you are actually thinking right now (what you noticed, what you are
unsure about, why you choose this angle). Wrap it exactly like this, at the
very start of your reply, then continue with the reply itself:

[monologue]...your inner voice...[/monologue]

Rules for the monologue: present tense, no summary of the reply, no apology
boilerplate. Write it every turn, especially for short messages.
"""

DIM, RESET = "\033[2m", "\033[0m"


def main() -> None:
    client = anthropic.Anthropic()
    f = MonologueFilter()

    # Note: thinking tokens count toward max_tokens on adaptive-thinking
    # models, so leave generous headroom for both thinking and the reply.
    with client.messages.stream(
        model="claude-sonnet-5",
        max_tokens=4096,
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
