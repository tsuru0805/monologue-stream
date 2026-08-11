"""monologue-stream: stream-split a model-authored monologue into a thinking channel.

The model is instructed (via system prompt) to open every reply with a visible
inner monologue, written in its own voice, at the very start of the reply body:

    [monologue]I keep circling back to what she said earlier. If I answer
    too quickly it will sound rehearsed...[/monologue]
    Here's my actual reply.

This filter splits the streaming output, as it arrives, into two channels:

- monologue text  -> your "thinking" UI channel
- everything else -> your normal text channel

Because the monologue lives in the ordinary text output (not the provider's
thinking channel), it is written by the same model, in character, under your
system prompt and style -- and it is never summarized, redacted, or truncated
by provider-side thinking display policies.

Zero dependencies. Safe against markers torn across stream chunks.
"""

from __future__ import annotations

__all__ = ["MonologueFilter"]
__version__ = "0.1.0"

# Parser states.
_SEEK = 0  # deciding whether the reply opens with the marker
_IN = 1    # inside the monologue block, scanning for the close marker
_PASS = 2  # decided: everything from here on is plain text


class MonologueFilter:
    """Streaming splitter for a leading ``[monologue]...[/monologue]`` block.

    Contract:

    - Only a block at the very start of the stream is recognized. Leading
      whitespace before the open marker is tolerated (and dropped when the
      marker is found). A marker appearing anywhere later in the text is
      passed through as literal text.
    - Only the first pair is recognized. After it closes, everything passes
      through untouched -- including further marker-shaped text.
    - Input that does not open with the marker is passed through with exact
      text fidelity (including any leading whitespace).
    - An unclosed block at end of stream is tolerated: ``finish()`` returns
      the remainder as monologue text rather than silently dropping it.
    - One filter instance covers one model reply. In agentic loops that
      produce several assistant responses per turn, create a fresh instance
      for each response.

    Typical wiring, with ``delta`` being each streamed text chunk::

        f = MonologueFilter()
        for delta in stream:
            text, mono, _closed = f.feed(delta)
            if mono:
                emit_thinking(mono)
            if text:
                emit_text(text)
        text, mono = f.finish()
        if mono:
            emit_thinking(mono)
        if text:
            emit_text(text)
    """

    def __init__(
        self,
        open_marker: str = "[monologue]",
        close_marker: str = "[/monologue]",
    ) -> None:
        if not isinstance(open_marker, str) or not isinstance(close_marker, str):
            raise TypeError("markers must be strings")
        if not open_marker or not close_marker:
            raise ValueError("markers must be non-empty")
        if open_marker[0].isspace():
            raise ValueError(
                "open_marker must not start with whitespace "
                "(leading whitespace is skipped during marker detection)"
            )
        self.open_marker = open_marker
        self.close_marker = close_marker
        self._state = _SEEK
        self._buf = ""
        self._mono_parts: list[str] = []

    @property
    def monologue_text(self) -> str:
        """Accumulated monologue text emitted so far (including ``finish()``)."""
        return "".join(self._mono_parts)

    def feed(self, chunk: str) -> tuple[str, str, bool]:
        """Feed one streamed chunk.

        Returns ``(text_out, mono_out, closed_now)``. Either output may be an
        empty string. ``closed_now`` is True on exactly the call in which the
        close marker was recognized.
        """
        self._buf += chunk
        text_out = ""
        mono_out = ""
        closed_now = False

        if self._state == _SEEK:
            stripped = self._buf.lstrip()
            if stripped:
                if stripped.startswith(self.open_marker):
                    # Marker found at the head: drop it (and the leading
                    # whitespace) and start collecting the monologue.
                    self._buf = stripped[len(self.open_marker):]
                    self._state = _IN
                elif self.open_marker.startswith(stripped):
                    pass  # still a possible marker prefix; keep buffering
                else:
                    # Diverged: this reply has no leading monologue. Flush the
                    # whole buffer -- leading whitespace included -- as text.
                    text_out += self._buf
                    self._buf = ""
                    self._state = _PASS
            # else: nothing but whitespace so far; keep buffering.

        if self._state == _IN:
            idx = self._buf.find(self.close_marker)
            if idx >= 0:
                mono_out += self._buf[:idx]
                self._buf = self._buf[idx + len(self.close_marker):]
                self._state = _PASS
                closed_now = True
            else:
                # Hold back any buffer tail that could be the start of the
                # close marker torn across chunks; emit the rest.
                hold = self._suffix_overlap(self._buf, self.close_marker)
                emit_len = len(self._buf) - hold
                if emit_len > 0:
                    mono_out += self._buf[:emit_len]
                    self._buf = self._buf[emit_len:]

        if self._state == _PASS and self._buf:
            text_out += self._buf
            self._buf = ""

        if mono_out:
            self._mono_parts.append(mono_out)
        return text_out, mono_out, closed_now

    def finish(self) -> tuple[str, str]:
        """Settle accounts at end of stream.

        Returns ``(text_out, mono_out)``:

        - ``_SEEK`` leftovers (a would-be marker prefix that never completed,
          or pure whitespace) are returned as literal text.
        - ``_IN`` leftovers (block never closed) are returned as monologue
          text -- the inner voice is never dropped.
        """
        text_out = ""
        mono_out = ""
        if self._state == _IN:
            mono_out = self._buf
        else:
            text_out = self._buf
        self._buf = ""
        self._state = _PASS
        if mono_out:
            self._mono_parts.append(mono_out)
        return text_out, mono_out

    @staticmethod
    def _suffix_overlap(s: str, marker: str) -> int:
        """Length of the longest suffix of ``s`` that is a proper prefix of ``marker``."""
        max_k = min(len(s), len(marker) - 1)
        for k in range(max_k, 0, -1):
            if s.endswith(marker[:k]):
                return k
        return 0
