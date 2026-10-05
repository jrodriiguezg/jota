"""Pruebas unitarias para el detector continuo de wake word (manos libres)."""

from unittest.mock import MagicMock, patch

import numpy as np

from jota.wakeword import WakeWordListener


class TestWakeWordListener:
    """Verifica el ciclo de vida y la logica VAD de WakeWordListener."""

    def test_init_defaults(self):
        callback = MagicMock()
        listener = WakeWordListener(on_wake=callback)

        assert listener.on_wake == callback
        assert listener.is_running is False
        assert listener.is_paused is False
        assert listener.sample_rate == 16000
        assert listener._in_speech is False

    def test_pause_and_resume(self):
        callback = MagicMock()
        listener = WakeWordListener(on_wake=callback)

        listener._speech_frames.append(np.zeros((1024, 1), dtype=np.int16))
        listener._in_speech = True
        listener._queue.put([np.zeros((1024, 1), dtype=np.int16)])

        listener.pause()
        assert listener.is_paused is True
        assert listener._in_speech is False
        assert len(listener._speech_frames) == 0
        assert listener._queue.empty()

        listener.resume()
        assert listener.is_paused is False
        assert listener._in_speech is False

    def test_audio_callback_vad_cycle(self):
        """Simula entrada de audio: silencio -> voz -> silencio para verificar despacho VAD."""
        callback = MagicMock()
        level_cb = MagicMock()
        listener = WakeWordListener(
            on_wake=callback,
            level_callback=level_cb,
            vad_threshold=0.015,
            silence_timeout=0.1,  # 0.1s para disparar rapido en test (~1-2 bloques)
            sample_rate=16000,
        )
        listener._running = True

        silence_block = np.zeros((1024, 1), dtype=np.int16)
        # Generar bloque de voz fuerte (amplitud ~10000 sobre int16)
        speech_block = (np.ones((1024, 1), dtype=np.int16) * 12000)

        # 1. Enviar silencio inicial
        listener._audio_callback(silence_block, 1024, None, None)
        assert listener._in_speech is False
        assert listener._queue.empty()

        # 2. Enviar 2 bloques de voz para confirmar inicio de habla
        listener._audio_callback(speech_block, 1024, None, None)
        listener._audio_callback(speech_block, 1024, None, None)
        assert listener._in_speech is True
        assert len(listener._speech_frames) >= 2
        level_cb.assert_called()

        # 3. Enviar bloques de silencio para superar el umbral de silencio
        for _ in range(listener._silence_blocks_needed + 1):
            listener._audio_callback(silence_block, 1024, None, None)

        # 4. Debe haberse despachado a la cola y reseteado _in_speech
        assert listener._in_speech is False
        assert not listener._queue.empty()
        dispatched_frames = listener._queue.get_nowait()
        assert len(dispatched_frames) >= 2

    @patch("jota.stt.transcribe")
    @patch("jota.audio._save_wav")
    def test_process_speech_frames_wake_word_detected(self, mock_save, mock_transcribe):
        callback = MagicMock()
        listener = WakeWordListener(on_wake=callback)
        listener._running = True

        # Crear bloque con duracion suficiente (>0.4s a 16kHz = >6400 muestras)
        big_block = np.zeros((8000, 1), dtype=np.int16)
        mock_transcribe.return_value = "Jota abre la terminal"

        listener._process_speech_frames([big_block])
        callback.assert_called_once_with("abre la terminal")

    @patch("jota.stt.transcribe")
    @patch("jota.audio._save_wav")
    def test_process_speech_frames_no_wake_word(self, mock_save, mock_transcribe):
        callback = MagicMock()
        listener = WakeWordListener(on_wake=callback)
        listener._running = True

        big_block = np.zeros((8000, 1), dtype=np.int16)
        mock_transcribe.return_value = "buenas tardes a todos"

        listener._process_speech_frames([big_block])
        callback.assert_not_called()

    @patch("sounddevice.InputStream")
    def test_start_and_stop(self, mock_stream_cls):
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream

        callback = MagicMock()
        listener = WakeWordListener(on_wake=callback)

        listener.start()
        assert listener.is_running is True
        mock_stream.start.assert_called_once()

        listener.stop()
        assert listener.is_running is False
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
