import numpy as np

from jota.vad import SileroVAD


def test_silero_vad_init():
    vad = SileroVAD()
    assert vad.threshold == 0.5
    assert vad.sample_rate == 16000
    # Si onnxruntime y el modelo estan presentes, is_available debe ser True
    assert isinstance(vad.is_available, bool)


def test_silero_vad_silence_detection():
    vad = SileroVAD()
    # Bloque de silencio puro (ceros)
    silence = np.zeros(1024, dtype=np.int16)
    prob = vad.speech_probability(silence)
    assert 0.0 <= prob <= 0.15
    assert vad.is_speech(silence) is False


def test_silero_vad_reset_state():
    vad = SileroVAD()
    vad.reset()
    assert np.all(vad._state == 0.0)


def test_silero_vad_fallback_without_session(monkeypatch):
    vad = SileroVAD()
    monkeypatch.setattr(vad, "_available", False)
    monkeypatch.setattr(vad, "_session", None)

    silence = np.zeros(512, dtype=np.int16)
    assert vad.is_speech(silence) is False

    # Ruido / señal de alta amplitud
    loud = np.full(512, 10000, dtype=np.int16)
    assert vad.speech_probability(loud) > 0.0
