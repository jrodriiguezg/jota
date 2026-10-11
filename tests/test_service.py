"""Tests para CopilotVoiceService."""

from unittest.mock import MagicMock, patch

from jota.service import CopilotVoiceService


class TestCopilotVoiceService:
    @patch("jota.hotkey.find_keyboards")
    def test_service_init_and_stop(self, mock_find):
        mock_orb = MagicMock()
        service = CopilotVoiceService(orb=mock_orb)

        assert service.orb == mock_orb
        assert not service._busy

        service.stop()
        mock_orb.set_state.assert_called_with("idle")
        mock_orb.quit.assert_called_once()

    @patch("jota.hotkey.find_keyboards")
    def test_key_press_and_release(self, mock_find):
        mock_orb = MagicMock()
        service = CopilotVoiceService(orb=mock_orb)
        service.recorder = MagicMock()
        service.recorder.is_recording = True

        service._on_key_press()
        mock_orb.set_state.assert_called_with("listening", 0.0)
        service.recorder.start.assert_called_once()

        with patch("threading.Thread") as mock_thread:
            service._on_key_release()
            mock_thread.assert_called_once()

    @patch("jota.stt.transcribe")
    @patch("jota.tools.handle_intent")
    @patch("jota.tts.speak")
    def test_do_process_fast_intent(self, mock_speak, mock_intent, mock_transcribe, tmp_path):
        mock_orb = MagicMock()
        service = CopilotVoiceService(orb=mock_orb)

        dummy_wav = tmp_path / "audio.wav"
        dummy_wav.write_bytes(b"RIFF dummy")

        service.recorder.stop = MagicMock(return_value=dummy_wav)
        mock_transcribe.return_value = "sube el volumen"
        mock_intent.return_value = (True, "Volumen subido al 85%.")

        service._do_process()

        mock_intent.assert_called_with("sube el volumen")
        mock_speak.assert_called_with("Volumen subido al 85%.")
        mock_orb.set_state.assert_any_call("thinking")
        mock_orb.set_state.assert_any_call("speaking")
        mock_orb.set_state.assert_any_call("idle")

    @patch("jota.tools.handle_intent")
    @patch("jota.tts.speak")
    def test_process_wake_command_direct(self, mock_speak, mock_intent):
        mock_orb = MagicMock()
        service = CopilotVoiceService(orb=mock_orb, enable_handsfree=True)
        service.wake_listener = MagicMock()

        mock_intent.return_value = (True, "Dolphin abierto.")
        service._process_wake_command("abre el explorador")

        service.wake_listener.pause.assert_called_once()
        service.wake_listener.resume.assert_called_once()
        mock_intent.assert_called_with("abre el explorador")
        mock_speak.assert_called_with("Dolphin abierto.")
        mock_orb.set_state.assert_any_call("thinking")
        mock_orb.set_state.assert_any_call("speaking")
        mock_orb.set_state.assert_any_call("idle")

    @patch("jota.stt.transcribe")
    @patch("jota.tools.handle_intent")
    @patch("jota.tts.speak")
    def test_process_wake_command_empty_with_follow_up(
        self, mock_speak, mock_intent, mock_transcribe, tmp_path
    ):
        mock_orb = MagicMock()
        service = CopilotVoiceService(orb=mock_orb, enable_handsfree=True)
        service.wake_listener = MagicMock()

        dummy_followup = tmp_path / "followup.wav"
        dummy_followup.write_bytes(b"RIFF dummy")
        service._record_follow_up = MagicMock(return_value=dummy_followup)

        mock_transcribe.return_value = "pon la música"
        mock_intent.return_value = (True, "Reproduciendo música.")

        service._process_wake_command("")

        mock_orb.set_state.assert_any_call("listening", 0.0)
        service._record_follow_up.assert_called_once_with(timeout=5.0)
        mock_transcribe.assert_called_once_with(dummy_followup)
        mock_intent.assert_called_with("pon la música")
        mock_speak.assert_called_with("Reproduciendo música.")

    def test_key_press_pauses_wake_listener(self):
        mock_orb = MagicMock()
        service = CopilotVoiceService(orb=mock_orb, enable_handsfree=True)
        service.wake_listener = MagicMock()
        service.recorder = MagicMock()

        service._on_key_press()
        service.wake_listener.pause.assert_called_once()

    def test_audio_ducking_lifecycle(self):
        mock_orb = MagicMock()
        service = CopilotVoiceService(orb=mock_orb)
        service.ducker = MagicMock()

        service._on_key_press()
        service.ducker.duck.assert_called_once()

        service.stop()
        service.ducker.unduck.assert_called()


class TestAudioDucker:
    @patch("subprocess.run")
    def test_duck_playerctl_playing(self, mock_run):
        from jota.audio import AudioDucker

        ducker = AudioDucker()
        mock_run.side_effect = [
            MagicMock(stdout="Playing\n", returncode=0),
            MagicMock(stdout="0.85\n", returncode=0),
            MagicMock(returncode=0),
        ]

        assert ducker.duck() is True
        assert ducker.is_ducked is True
        assert ducker.duck_mode == "playerctl"
        assert ducker.saved_playerctl_vol == 0.85

        # Restore
        mock_run.side_effect = [MagicMock(returncode=0)]
        assert ducker.unduck() is True
        assert ducker.is_ducked is False
        assert ducker.duck_mode is None

    @patch("subprocess.run")
    def test_duck_wpctl_fallback(self, mock_run):
        from jota.audio import AudioDucker

        ducker = AudioDucker()
        mock_run.side_effect = [
            MagicMock(stdout="No players found\n", returncode=1),
            MagicMock(stdout="Volume: 0.70\n", returncode=0),
            MagicMock(returncode=0),
        ]

        assert ducker.duck() is True
        assert ducker.is_ducked is True
        assert ducker.duck_mode == "wpctl"
        assert ducker.saved_sink_vol == 0.70

        # Unduck with mode check
        assert ducker.unduck(only_if_mode="playerctl") is False
        assert ducker.is_ducked is True

        assert ducker.unduck(only_if_mode="wpctl") is True
        assert ducker.is_ducked is False

