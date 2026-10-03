"""Tests de utilidades del modulo LLM."""

from jota.llm import clean_text_for_tts


def test_clean_text_strips_markdown():
    raw = "**Hola**, soy *Jota*. ### Encabezado\n- Item 1\n`codigo`"
    cleaned = clean_text_for_tts(raw)
    assert "*" not in cleaned
    assert "#" not in cleaned
    assert "`" not in cleaned
    assert "-" not in cleaned
    assert "Hola, soy Jota." in cleaned


def test_clean_text_strips_think_blocks():
    raw = "<think> Thinking process in english... </think> Hola, como estas?"
    cleaned = clean_text_for_tts(raw)
    assert "<think>" not in cleaned
    assert "</think>" not in cleaned
    assert "Thinking process" not in cleaned
    assert cleaned == "Hola, como estas?"

