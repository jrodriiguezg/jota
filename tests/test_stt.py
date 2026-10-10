from unittest.mock import patch

from jota.stt import extract_wake_word, strip_wake_word


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


class TestExtractWakeWord:
    """Prueba la funcion extract_wake_word para deteccion manos libres."""

    def test_extract_jota_con_comando(self):
        has_wake, cmd = extract_wake_word("Jota abre el explorador")
        assert has_wake is True
        assert cmd == "abre el explorador"

    def test_extract_solo_wake_word(self):
        has_wake, cmd = extract_wake_word("Jota")
        assert has_wake is True
        assert cmd == ""

        has_wake_j, cmd_j = extract_wake_word("J")
        assert has_wake_j is True
        assert cmd_j == ""

    def test_extract_hota_variante(self):
        has_wake, cmd = extract_wake_word("Hota pon la música")
        assert has_wake is True
        assert cmd == "pon la música"

    def test_extract_sin_wake_word(self):
        has_wake, cmd = extract_wake_word("hola cómo estás")
        assert has_wake is False
        assert cmd == "hola cómo estás"

        has_wake_2, cmd_2 = extract_wake_word("hoy hace buen día")
        assert has_wake_2 is False
        assert cmd_2 == "hoy hace buen día"

    def test_extract_cadena_vacia(self):
        has_wake, cmd = extract_wake_word("   ")
        assert has_wake is False
        assert cmd == ""

    @patch("subprocess.run")
    def test_transcribe_filters_silence_brackets(self, mock_run, tmp_path):
        from jota import stt

        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "[SILENCIO]"
        fake_wav = tmp_path / "test.wav"
        fake_wav.write_bytes(b"RIFFdata")

        result = stt.transcribe(fake_wav)
        assert result is None


