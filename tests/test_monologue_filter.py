"""Tests for MonologueFilter.

Run: python -m pytest tests/ -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from monologue_filter import MonologueFilter

OPEN = "[monologue]"
CLOSE = "[/monologue]"


def run(chunks, **kwargs):
    """Feed chunks through a fresh filter; return (text, mono, closed_any, filter)."""
    f = MonologueFilter(**kwargs)
    text, mono, closed_any = [], [], False
    for c in chunks:
        t, m, closed = f.feed(c)
        text.append(t)
        mono.append(m)
        closed_any = closed_any or closed
    t, m = f.finish()
    text.append(t)
    mono.append(m)
    return "".join(text), "".join(mono), closed_any, f


def every_split(s):
    """All two-part splits of s, including the trivial ones."""
    return [(s[:i], s[i:]) for i in range(len(s) + 1)]


def char_by_char(s):
    return list(s)


class TestBasics:
    def test_whole_block_single_feed(self):
        text, mono, closed, _ = run([f"{OPEN}abc{CLOSE}def"])
        assert mono == "abc"
        assert text == "def"
        assert closed is True

    def test_marker_torn_across_chunks(self):
        text, mono, closed, _ = run(["[mono", "logue]a", "bc[/mono", "logue]d"])
        assert mono == "abc"
        assert text == "d"
        assert closed is True

    def test_char_by_char(self):
        src = f"{OPEN}inner voice{CLOSE}outer text"
        text, mono, closed, _ = run(char_by_char(src))
        assert mono == "inner voice"
        assert text == "outer text"
        assert closed is True

    def test_every_two_part_split(self):
        src = f"{OPEN}inner voice{CLOSE}outer text"
        for a, b in every_split(src):
            text, mono, closed, _ = run([a, b])
            assert mono == "inner voice", (a, b)
            assert text == "outer text", (a, b)
            assert closed is True


class TestPassthrough:
    def test_no_marker_byte_identical(self):
        src = "hello [world] this has [brackets] and ]stray[ pieces"
        for a, b in every_split(src):
            text, mono, _, _ = run([a, b])
            assert text == src, (a, b)
            assert mono == ""

    def test_near_prefix_divergence(self):
        text, mono, _, _ = run(["[mood]rest of text"])
        assert text == "[mood]rest of text"
        assert mono == ""

    def test_unfinished_prefix_at_eof(self):
        text, mono, _, _ = run(["[m"])
        assert text == "[m"
        assert mono == ""

    def test_mid_text_marker_is_literal(self):
        src = f"hello{OPEN}x{CLOSE}"
        text, mono, _, _ = run([src])
        assert text == src
        assert mono == ""

    def test_whitespace_only_stream(self):
        text, mono, _, _ = run(["  \n", "\t "])
        assert text == "  \n\t "
        assert mono == ""

    def test_empty_chunks(self):
        text, mono, closed, _ = run(["", f"{OPEN}a", "", f"{CLOSE}b", ""])
        assert mono == "a"
        assert text == "b"
        assert closed is True


class TestEdges:
    def test_leading_whitespace_tolerated(self):
        text, mono, closed, _ = run([f"\n {OPEN}a{CLOSE}b"])
        assert mono == "a"
        assert text == "b"
        assert closed is True

    def test_unclosed_at_eof_keeps_inner_voice(self):
        text, mono, closed, _ = run([f"{OPEN}abc"])
        assert mono == "abc"
        assert text == ""
        assert closed is False

    def test_only_first_pair_recognized(self):
        src = f"{OPEN}a{CLOSE}b{OPEN}c{CLOSE}"
        text, mono, _, _ = run([src])
        assert mono == "a"
        assert text == f"b{OPEN}c{CLOSE}"

    def test_closed_now_fires_once_on_the_right_call(self):
        f = MonologueFilter()
        _, _, closed = f.feed(f"{OPEN}abc")
        assert closed is False
        _, _, closed = f.feed(CLOSE[:4])
        assert closed is False
        _, _, closed = f.feed(CLOSE[4:] + "tail")
        assert closed is True
        _, _, closed = f.feed("more")
        assert closed is False

    def test_monologue_text_accumulates(self):
        _, _, _, f = run([f"{OPEN}one ", "two", f"{CLOSE}body"])
        assert f.monologue_text == "one two"

    def test_monologue_text_includes_unclosed_tail(self):
        _, _, _, f = run([f"{OPEN}kept"])
        assert f.monologue_text == "kept"

    def test_custom_markers(self):
        text, mono, closed, _ = run(
            ["<think>a", "b</th", "ink>c"],
            open_marker="<think>",
            close_marker="</think>",
        )
        assert mono == "ab"
        assert text == "c"
        assert closed is True

    def test_empty_marker_rejected(self):
        with pytest.raises(ValueError):
            MonologueFilter(open_marker="")
        with pytest.raises(ValueError):
            MonologueFilter(close_marker="")

    def test_whitespace_leading_open_marker_rejected(self):
        with pytest.raises(ValueError):
            MonologueFilter(open_marker=" [monologue]")

    def test_non_string_marker_rejected(self):
        with pytest.raises(TypeError):
            MonologueFilter(open_marker=123)  # type: ignore[arg-type]

    def test_empty_monologue_block(self):
        text, mono, closed, _ = run([f"{OPEN}{CLOSE}body"])
        assert mono == ""
        assert text == "body"
        assert closed is True


class TestPerCallEmission:
    """Liveness: the monologue must stream out per call, not buffer to the end."""

    def test_mono_emitted_immediately_when_no_close_prefix_in_tail(self):
        f = MonologueFilter()
        _, mono, _ = f.feed(f"{OPEN}hello world")
        assert mono == "hello world"  # tail "d" is no close-marker prefix: emit all

    def test_exact_tail_holdback_on_partial_close_prefix(self):
        f = MonologueFilter()
        _, mono, _ = f.feed(f"{OPEN}abc[/mono")
        assert mono == "abc"  # "[/mono" held back as a possible close prefix

    def test_false_close_prefix_released_on_divergence(self):
        f = MonologueFilter()
        f.feed(f"{OPEN}abc[/mono")
        _, mono, closed = f.feed("X")
        assert mono == "[/monoX"  # diverged: held tail released, nothing lost
        assert closed is False
        assert f.monologue_text == "abc[/monoX"

    def test_partial_close_prefix_at_finish_goes_to_mono(self):
        f = MonologueFilter()
        f.feed(f"{OPEN}abc[/mon")
        _, mono = f.finish()
        assert mono == "[/mon"
        assert f.monologue_text == "abc[/mon"
