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


def test_clean_text_strips_multiline_empty_think_blocks():
    raw = "<think>\n\n</think>\n\nHola! Como te va?"
    cleaned = clean_text_for_tts(raw)
    assert cleaned == "Hola! Como te va?"


def test_get_effective_system_prompt(monkeypatch):
    import jota.llm as llm_module

    monkeypatch.setattr(llm_module, "LLM_ENABLE_THINKING", False)
    prompt_no_think = llm_module.get_effective_system_prompt()
    assert prompt_no_think.endswith("/no_think")

    monkeypatch.setattr(llm_module, "LLM_ENABLE_THINKING", True)
    prompt_think = llm_module.get_effective_system_prompt()
    assert prompt_think.endswith("/think")


def test_clean_text_strips_tool_lines():
    raw = "TOOL: volume_control(action='up')\nSubo el volumen enseguida."
    cleaned = clean_text_for_tts(raw)
    assert "TOOL:" not in cleaned
    assert "volume_control" not in cleaned
    assert cleaned == "Subo el volumen enseguida."

    # Si solo habia la linea TOOL, debe quedar vacio
    only_tool = "TOOL: volumecontrol(action='up')"
    assert clean_text_for_tts(only_tool) == ""



