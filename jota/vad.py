"""
Detector de actividad de voz (Voice Activity Detection - VAD) con Silero VAD.
Ejecuta inferencia neuronal ultra-ligera en CPU con ONNX Runtime (~0.2ms por bloque)
con degradacion automatica a analisis RMS adaptativo si el modelo o ONNX no estan disponibles.
"""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Rutas candidatas para el modelo Silero VAD en ONNX
_CANDIDATE_MODEL_PATHS = [
    Path(__file__).parent.parent / "data/models/silero_vad.onnx",
    Path.home() / ".cache/jota/models/silero_vad.onnx",
    Path("/app/models/silero_vad.onnx"),
]


class SileroVAD:
    """
    Detector de voz en tiempo real basado en el modelo neural Silero VAD v5.
    Procesa bloques a 16kHz y mantiene el estado recurrente para maxima precision temporal.
    """

    def __init__(
        self,
        model_path: Path | str | None = None,
        threshold: float = 0.5,
        sample_rate: int = 16000,
    ):
        self.threshold = threshold
        self.sample_rate = sample_rate
        self._session = None
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._sr_tensor = np.array(sample_rate, dtype=np.int64)
        self._available = False

        self._init_model(model_path)

    def _init_model(self, model_path: Path | str | None) -> None:
        """Inicializa la sesion de ONNX Runtime si esta disponible."""
        try:
            import onnxruntime as ort
        except ImportError:
            logger.debug("onnxruntime no instalado; usando VAD adaptativo por energia RMS.")
            return

        resolved_path = None
        if model_path:
            p = Path(model_path)
            if p.is_file():
                resolved_path = p

        if not resolved_path:
            for cand in _CANDIDATE_MODEL_PATHS:
                if cand.is_file():
                    resolved_path = cand
                    break

        if not resolved_path:
            logger.debug("Modelo silero_vad.onnx no encontrado; usando fallback RMS.")
            return

        try:
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 1
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(
                str(resolved_path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            self._available = True
            logger.info("Silero VAD inicializado exitosamente desde %s", resolved_path)
        except Exception as e:
            logger.warning("Error cargando modelo Silero VAD: %s", e)
            self._session = None
            self._available = False

    @property
    def is_available(self) -> bool:
        """Devuelve True si el modelo neural Silero VAD esta activo."""
        return self._available

    def reset(self) -> None:
        """Reinicia el estado recurrente del modelo (llamado al cambiar de locucion)."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)

    def speech_probability(self, chunk: np.ndarray) -> float:
        """
        Calcula la probabilidad de presencia de voz humana en el bloque de audio.
        Devuelve un valor entre 0.0 y 1.0.
        """
        if chunk is None or len(chunk) == 0:
            return 0.0

        # Si Silero VAD no esta disponible, calcular probabilidad aproximada via RMS
        if not self._available or self._session is None:
            raw = chunk.astype(np.float32)
            rms = float(np.sqrt(np.mean(raw**2)))
            if chunk.dtype == np.int16 or np.max(np.abs(raw)) > 1.5:
                rms = rms / 32768.0
            # Mapear RMS relativo a un rango [0.0, 1.0]
            return min(1.0, max(0.0, rms * 35.0))

        # Convertir a float32 mono en rango [-1.0, 1.0]
        if chunk.dtype == np.int16:
            audio_f32 = chunk.astype(np.float32) / 32768.0
        else:
            audio_f32 = chunk.astype(np.float32)
            max_val = np.max(np.abs(audio_f32))
            if max_val > 1.0:
                audio_f32 = audio_f32 / 32768.0

        if audio_f32.ndim > 1:
            audio_f32 = audio_f32.flatten()

        # Silero VAD v5 requiere fragmentos de exactamente 512 muestras a 16kHz
        chunk_size = 512
        if len(audio_f32) < chunk_size:
            padded = np.zeros(chunk_size, dtype=np.float32)
            padded[: len(audio_f32)] = audio_f32
            slices = [padded]
        else:
            slices = [
                audio_f32[i : i + chunk_size]
                for i in range(0, len(audio_f32) - chunk_size + 1, chunk_size)
            ]
            if not slices:
                slices = [audio_f32[:chunk_size]]

        max_prob = 0.0
        try:
            for s in slices:
                tensor_in = s.reshape(1, chunk_size)
                outputs = self._session.run(
                    None,
                    {
                        "input": tensor_in,
                        "state": self._state,
                        "sr": self._sr_tensor,
                    },
                )
                prob = float(outputs[0][0][0]) if outputs[0].ndim > 1 else float(outputs[0][0])
                if len(outputs) > 1:
                    self._state = outputs[1]
                if prob > max_prob:
                    max_prob = prob
        except Exception as e:
            logger.debug("Error en inferencia Silero VAD: %s", e)
            return 0.0

        return max_prob

    def is_speech(self, chunk: np.ndarray, threshold: float | None = None) -> bool:
        """Determina si el bloque contiene voz por encima del umbral de decision."""
        th = threshold if threshold is not None else self.threshold
        return self.speech_probability(chunk) >= th
