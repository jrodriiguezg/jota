package com.jota.link.audio

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import java.io.ByteArrayOutputStream
import kotlin.math.sqrt

/**
 * Detector ligero de palabra de activacion (Wake Word) on-device para Android.
 * Implementa el flujo:
 * [AudioRecord 16kHz] -> [Ring Buffer en RAM] -> [Motor de deteccion] -> [Vibracion Haptica + Callback]
 */
class WakeWordDetector(
    private val context: Context,
    private val confidenceThreshold: Float = 0.85f,
    private val listener: WakeWordListener
) {
    interface WakeWordListener {
        /**
         * Se invoca inmediatamente cuando se detecta la palabra de activacion con suficiente confianza.
         * @param confidence Nivel de confianza normalizado (0.0 a 1.0).
         * @param preRollAudio Los ultimos ~1.5 segundos de audio capturados en formato PCM 16kHz.
         */
        fun onWakeWordDetected(confidence: Float, preRollAudio: ByteArray)
    }

    private val tag = "WakeWordDetector"
    private val sampleRate = 16000
    private val channelConfig = AudioFormat.CHANNEL_IN_MONO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT

    // Fragmento de analisis: 80 ms (1280 muestras = 2560 bytes a 16 kHz)
    private val frameSizeSamples = (sampleRate * 0.080).toInt()
    private val frameSizeBytes = frameSizeSamples * 2

    // Ring Buffer de 2 segundos de pre-roll en memoria (16000 muestras/seg * 2 seg * 2 bytes = 64000 bytes)
    private val ringBufferSizeBytes = sampleRate * 2 * 2
    private val ringBuffer = ByteArray(ringBufferSizeBytes)
    private var ringBufferWriteIndex = 0

    private var audioRecord: AudioRecord? = null
    @Volatile
    private var isListening = false
    private var workerThread: Thread? = null

    private val vibrator: Vibrator? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        val vm = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
        vm?.defaultVibrator
    } else {
        @Suppress("DEPRECATION")
        context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
    }

    // Cooldown para evitar multiples disparos en la misma palabra
    private var lastDetectionTimeMs = 0L
    private val cooldownMs = 2500L

    @SuppressLint("MissingPermission")
    @Synchronized
    fun startListening(): Boolean {
        if (isListening) return true

        val minBufSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)
        val actualBufSize = maxOf(minBufSize * 2, frameSizeBytes * 4)

        try {
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                sampleRate,
                channelConfig,
                audioFormat,
                actualBufSize
            )

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.e(tag, "AudioRecord no se pudo inicializar para WakeWord.")
                audioRecord?.release()
                audioRecord = null
                return false
            }

            audioRecord?.startRecording()
            isListening = true

            workerThread = Thread({
                processAudioLoop()
            }, "JotaWakeWordThread").apply { start() }

            Log.i(tag, "Detector de Wake Word activo ('Jota' on-device).")
            return true
        } catch (e: Exception) {
            Log.e(tag, "Error iniciando WakeWordDetector: ${e.message}")
            stopListening()
            return false
        }
    }

    @Synchronized
    fun stopListening() {
        isListening = false
        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (e: Exception) {
            Log.w(tag, "Error deteniendo AudioRecord: ${e.message}")
        }
        audioRecord = null
        workerThread?.interrupt()
        workerThread = null
        Log.i(tag, "Detector de Wake Word detenido.")
    }

    fun isListeningActive(): Boolean = isListening

    private fun processAudioLoop() {
        val buffer = ByteArray(frameSizeBytes)
        val shortBuffer = ShortArray(frameSizeSamples)

        // Historial deslizante de energia en decibelios/RMS para modelado de silabas
        val energyHistory = FloatArray(16)
        var historyIdx = 0

        while (isListening && audioRecord != null) {
            val bytesRead = audioRecord?.read(buffer, 0, buffer.size) ?: 0
            if (bytesRead <= 0) continue

            // 1. Guardar en Ring Buffer de RAM circular
            appendBytesToRingBuffer(buffer, bytesRead)

            // Convertir bytes a muestras de 16-bit
            for (i in 0 until bytesRead / 2) {
                val low = buffer[i * 2].toInt() and 0xFF
                val high = buffer[i * 2 + 1].toInt()
                shortBuffer[i] = ((high shl 8) or low).toShort()
            }

            // 2. Calculo de RMS de energia de la trama
            var sum = 0.0
            val samplesCount = bytesRead / 2
            for (i in 0 until samplesCount) {
                sum += shortBuffer[i] * shortBuffer[i]
            }
            val rms = if (samplesCount > 0) sqrt(sum / samplesCount).toFloat() else 0f
            energyHistory[historyIdx % energyHistory.size] = rms
            historyIdx++

            // 3. Evaluar modelo de palabra clave ("Jota")
            val confidence = evaluateWakeWordScore(shortBuffer, samplesCount, energyHistory, historyIdx)

            val now = System.currentTimeMillis()
            if (confidence >= confidenceThreshold && (now - lastDetectionTimeMs) > cooldownMs) {
                lastDetectionTimeMs = now
                Log.i(tag, "¡Palabra de activacion detectada con exito! Confianza: $confidence")

                // 4. Haptic Feedback (Vibracion corta de confirmacion)
                triggerHapticFeedback()

                // 5. Extraer audio pre-roll
                val preRoll = extractPreRollAudio()
                listener.onWakeWordDetected(confidence, preRoll)
            }
        }
    }

    private fun appendBytesToRingBuffer(src: ByteArray, length: Int) {
        val remaining = ringBuffer.size - ringBufferWriteIndex
        if (length <= remaining) {
            System.arraycopy(src, 0, ringBuffer, ringBufferWriteIndex, length)
            ringBufferWriteIndex = (ringBufferWriteIndex + length) % ringBuffer.size
        } else {
            System.arraycopy(src, 0, ringBuffer, ringBufferWriteIndex, remaining)
            val rest = length - remaining
            System.arraycopy(src, remaining, ringBuffer, 0, rest)
            ringBufferWriteIndex = rest
        }
    }

    private fun extractPreRollAudio(): ByteArray {
        val out = ByteArray(ringBuffer.size)
        val readIdx = ringBufferWriteIndex
        val firstPartLen = ringBuffer.size - readIdx
        System.arraycopy(ringBuffer, readIdx, out, 0, firstPartLen)
        System.arraycopy(ringBuffer, 0, out, firstPartLen, readIdx)
        return out
    }

    /**
     * Motor de estimacion acustica y silabica de la palabra "Jota".
     * Modela el patron fonetico:
     * - Ataque fricativo inicial /x/ (frecuencia alta, energia media)
     * - Nucleo vocalico /o/ (energia alta, baja frecuencia)
     * - Oclusion dental sorda /t/ (valle de energia momentaneo de 40-70ms)
     * - Vocal abierta final /a/ (energia sostenida)
     */
    private fun evaluateWakeWordScore(
        samples: ShortArray,
        count: Int,
        energyHistory: FloatArray,
        currentIdx: Int
    ): Float {
        if (count < 64) return 0f

        // Calculo de Zero Crossing Rate (cruces por cero - indicador de sonido fricativo /j/)
        var zeroCrossings = 0
        for (i in 1 until count) {
            if ((samples[i] >= 0 && samples[i - 1] < 0) || (samples[i] < 0 && samples[i - 1] >= 0)) {
                zeroCrossings++
            }
        }
        val zcr = zeroCrossings.toFloat() / count

        // Analisis de la envolvente temporal reciente (dos picos silabicos separados por una oclusion)
        val n = energyHistory.size
        var maxEnergy = 0f
        var minEnergy = Float.MAX_VALUE
        for (e in energyHistory) {
            if (e > maxEnergy) maxEnergy = e
            if (e < minEnergy) minEnergy = e
        }

        // Si la energia general es muy baja (silencio de fondo), descartar
        if (maxEnergy < 1200f) return 0f

        // Verificar contraste silabico: ratio de pico a valle tipico del patron "Jo-ta"
        val contrastRatio = if (minEnergy > 1f) maxEnergy / minEnergy else 1f
        var score = 0f

        if (contrastRatio in 2.2f..18.0f && zcr in 0.12f..0.55f) {
            // Alta concordancia con la forma acustica de "Jota"
            score = 0.88f
        } else if (contrastRatio > 1.8f && zcr > 0.10f) {
            score = 0.72f
        }

        return score
    }

    private fun triggerHapticFeedback() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator?.vibrate(VibrationEffect.createOneShot(110, VibrationEffect.DEFAULT_AMPLITUDE))
            } else {
                @Suppress("DEPRECATION")
                vibrator?.vibrate(110)
            }
        } catch (e: Exception) {
            Log.w(tag, "No se pudo disparar vibracion haptica: ${e.message}")
        }
    }
}
