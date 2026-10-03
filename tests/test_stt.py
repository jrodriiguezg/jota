"""Tests basicos de Fase 1."""

from jota.stt import strip_wake_word


class TestStripWakeWord:
    """Prueba la deteccion y limpieza del wake word."""

    def test_jota_simple(self):
        assert strip_wake_word("Jota qué hora es") == "qué hora es"

    def test_jota_con_coma(self):
        assert strip_wake_word("Jota, cómo estás") == "cómo estás"

    def test_jota_mayusculas(self):
        assert strip_wake_word("JOTA qué tiempo hace") == "qué tiempo hace"

    def test_hota_variante(self):
        """Whisper a veces transcribe 'Jota' como 'Hota'."""
        assert strip_wake_word("Hota cuéntame algo") == "cuéntame algo"

    def test_push_to_talk_sin_wake_word(self):
        """En modo push-to-talk (require_wake_word=False), no se exige wake word."""
        assert strip_wake_word("Cómo estás", require_wake_word=False) == "Cómo estás"
        assert strip_wake_word("abre una terminal", require_wake_word=False) == "abre una terminal"
        assert strip_wake_word("¿qué hora es?", require_wake_word=False) == "qué hora es?"

    def test_modo_estricto_sin_wake_word(self):
        """En modo estricto (require_wake_word=True), se ignora la frase sin wake word."""
        assert strip_wake_word("Cómo estás", require_wake_word=True) is None
        assert strip_wake_word("Juegos de mesa", require_wake_word=True) is None
        assert strip_wake_word("Jamás digas nunca", require_wake_word=True) is None

    def test_solo_wake_word(self):
        """Solo el wake word -> None (frase vacia)."""
        assert strip_wake_word("Jota") is None
        assert strip_wake_word("J") is None
        assert strip_wake_word("J,") is None

    def test_wake_word_con_signos(self):
        assert strip_wake_word("¡Jota! pon un temporizador") == "pon un temporizador"

    def test_j_letra_con_coma(self):
        """Whisper transcribe frecuentemente 'Jota' como 'J, ¿cómo estás?'."""
        assert strip_wake_word("J, ¿cómo estás?") == "cómo estás?"

    def test_j_letra_simple(self):
        assert strip_wake_word("J qué hora es") == "qué hora es"

