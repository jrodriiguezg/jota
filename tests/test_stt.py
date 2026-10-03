"""Tests basicos de Fase 1."""

from jota.stt import strip_wake_word


class TestStripWakeWord:
    """Prueba la detección y limpieza del wake word."""

    def test_jota_simple(self):
        assert strip_wake_word("Jota qué hora es") == "qué hora es"

    def test_jota_con_coma(self):
        assert strip_wake_word("Jota, cómo estás") == "cómo estás"

    def test_jota_mayusculas(self):
        assert strip_wake_word("JOTA qué tiempo hace") == "qué tiempo hace"

    def test_hota_variante(self):
        """Whisper a veces transcribe 'Jota' como 'Hota'."""
        assert strip_wake_word("Hota cuéntame algo") == "cuéntame algo"

    def test_sin_wake_word(self):
        """Sin wake word → None (no responder)."""
        assert strip_wake_word("Cómo estás") is None

    def test_solo_wake_word(self):
        """Sólo el wake word → None (frase vacía)."""
        assert strip_wake_word("Jota") is None

    def test_wake_word_con_signos(self):
        assert strip_wake_word("¡Jota! pon un temporizador") == "pon un temporizador"

    def test_j_letra_con_coma(self):
        """Whisper transcribe frecuentemente 'Jota' como 'J, ¿cómo estás?'."""
        assert strip_wake_word("J, ¿cómo estás?") == "cómo estás?"

    def test_j_letra_simple(self):
        assert strip_wake_word("J qué hora es") == "qué hora es"

    def test_j_no_confunde_palabras(self):
        """Palabras que empiezan por J no deben activar el asistente."""
        assert strip_wake_word("Juegos de mesa") is None
        assert strip_wake_word("Jamás digas nunca") is None

    def test_solo_letra_j(self):
        """Decir solo 'J' sin petición no debe procesarse."""
        assert strip_wake_word("J") is None
        assert strip_wake_word("J,") is None
