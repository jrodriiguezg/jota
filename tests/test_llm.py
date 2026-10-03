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
