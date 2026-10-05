package com.jota.link.service

import android.app.*
import android.content.*
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.RingtoneManager
import android.net.Uri
import android.os.*
import androidx.core.app.NotificationCompat
import com.jota.link.audio.AudioHelper
import com.jota.link.audio.WakeWordDetector
import com.jota.link.network.BridgeClient
import kotlinx.coroutines.*

class JotaBridgeService : Service(), BridgeClient.BridgeListener {
    private var bridgeClient: BridgeClient? = null
    private var vibrator: Vibrator? = null
    private var ringtone: android.media.Ringtone? = null

    private var wakeWordDetector: WakeWordDetector? = null
    private val audioHelper = AudioHelper()
    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private var lastSyncedClipboard: String = ""
    private var clipboardListener: ClipboardManager.OnPrimaryClipChangedListener? = null
    private var clipboardDebounceJob: Job? = null

    companion object {
        const val CHANNEL_ID = "jota_bridge_channel"
        const val NOTIFICATION_ID = 1001
        const val ACTION_STOP_ALARM = "com.jota.link.STOP_ALARM"
        const val ACTION_TOGGLE_WAKE_WORD = "com.jota.link.TOGGLE_WAKE_WORD"
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val vm = getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
            vm.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        }

        // Listener de portapapeles universal bidireccional con debounce
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
        if (cm != null) {
            clipboardListener = ClipboardManager.OnPrimaryClipChangedListener {
                val clip = cm.primaryClip
                if (clip != null && clip.itemCount > 0) {
                    val text = clip.getItemAt(0).text?.toString() ?: ""
                    if (text.isNotEmpty() && text != lastSyncedClipboard && text.length < 20000) {
                        clipboardDebounceJob?.cancel()
                        clipboardDebounceJob = serviceScope.launch {
                            delay(400)
                            if (text != lastSyncedClipboard) {
                                lastSyncedClipboard = text
                                bridgeClient?.sendClipboard(text)
                            }
                        }
                    }
                }
            }
            cm.addPrimaryClipChangedListener(clipboardListener)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP_ALARM) {
            stopAlarm()
            return START_STICKY
        }

        if (intent?.action == ACTION_TOGGLE_WAKE_WORD) {
            val enable = intent.getBooleanExtra("enable", false)
            setupWakeWord(enable)
            return START_STICKY
        }

        val baseUrl = intent?.getStringExtra("baseUrl") ?: "http://100.64.0.1:8765"
        val apiKey = intent?.getStringExtra("apiKey") ?: "jota-secret-tailscale-key"
        val deviceId = intent?.getStringExtra("deviceId") ?: "android_phone"
        val enableWakeWord = intent?.getBooleanExtra("enableWakeWord", false) ?: false

        startForeground(NOTIFICATION_ID, buildNotification("Conectando a Jota Bridge..."))

        bridgeClient?.disconnect()
        bridgeClient = BridgeClient(this, baseUrl, apiKey, deviceId).apply {
            listener = this@JotaBridgeService
            connectWebSocket()
        }

        setupWakeWord(enableWakeWord)

        return START_STICKY
    }

    override fun onConnected() {
        updateNotification("Conectado con Jota (PC)")
    }

    override fun onDisconnected() {
        updateNotification("Desconectado de Jota. Reconectando...")
    }

    override fun onRing(durationSeconds: Int) {
        val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val maxVol = am.getStreamMaxVolume(AudioManager.STREAM_ALARM)
        am.setStreamVolume(AudioManager.STREAM_ALARM, maxVol, 0)

        val alarmUri: Uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)

        ringtone = RingtoneManager.getRingtone(applicationContext, alarmUri)?.apply {
            audioAttributes = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build()
            play()
        }

        val pattern = longArrayOf(0, 500, 200, 500, 200, 1000)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator?.vibrate(VibrationEffect.createWaveform(pattern, 0))
        } else {
            @Suppress("DEPRECATION")
            vibrator?.vibrate(pattern, 0)
        }

        Handler(Looper.getMainLooper()).postDelayed({
            stopAlarm()
        }, durationSeconds * 1000L)
    }

    private fun stopAlarm() {
        try {
            ringtone?.stop()
            vibrator?.cancel()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    override fun onClipboardReceived(text: String) {
        if (text.isEmpty() || text == lastSyncedClipboard) return
        lastSyncedClipboard = text
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
        val clip = ClipData.newPlainText("Jota PC", text)
        cm?.setPrimaryClip(clip)
    }

    override fun onOpenUrl(url: String) {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        startActivity(intent)
    }

    override fun onTorch(enabled: Boolean) {
        try {
            val cm = getSystemService(Context.CAMERA_SERVICE) as? android.hardware.camera2.CameraManager
            val cameraId = cm?.cameraIdList?.firstOrNull()
            if (cm != null && cameraId != null) {
                cm.setTorchMode(cameraId, enabled)
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    override fun onSilent(silent: Boolean) {
        try {
            val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
            if (silent) {
                am.ringerMode = AudioManager.RINGER_MODE_SILENT
            } else {
                am.ringerMode = AudioManager.RINGER_MODE_NORMAL
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    override fun onReceiveFile(filename: String, remotePath: String, sizeBytes: Long) {
        kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
            try {
                val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                val destFile = java.io.File(downloadsDir, filename)
                val ok = bridgeClient?.downloadPcFile(remotePath, destFile) ?: false
                if (ok) {
                    Handler(Looper.getMainLooper()).post {
                        android.widget.Toast.makeText(
                            applicationContext,
                            "Archivo recibido: $filename en Descargas",
                            android.widget.Toast.LENGTH_LONG
                        ).show()
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    override fun onPcNotification(title: String, message: String) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val notif = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(message)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setAutoCancel(true)
            .build()
        nm.notify((System.currentTimeMillis() % 10000).toInt() + 2000, notif)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Jota Bridge Service",
                NotificationManager.IMPORTANCE_LOW
            )
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(text: String): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("JotaLink")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(text: String) {
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.notify(NOTIFICATION_ID, buildNotification(text))
    }

    private fun setupWakeWord(enable: Boolean) {
        if (!enable) {
            wakeWordDetector?.stopListening()
            wakeWordDetector = null
            return
        }
        if (wakeWordDetector != null && wakeWordDetector?.isListeningActive() == true) return

        wakeWordDetector = WakeWordDetector(this, 0.85f, object : WakeWordDetector.WakeWordListener {
            override fun onWakeWordDetected(confidence: Float, preRollAudio: ByteArray) {
                updateNotification("¡Jota detectado! Escuchando orden...")
                serviceScope.launch {
                    try {
                        wakeWordDetector?.stopListening()
                        audioHelper.startRecording()
                        delay(3500)
                        val voiceWav = audioHelper.stopRecording()
                        updateNotification("Procesando con Jota en PC...")

                        val resp = bridgeClient?.askVoice(voiceWav)
                        val reply = resp?.optString("response_text", "") ?: ""
                        if (reply.isNotEmpty()) {
                            onPcNotification("Jota", reply)
                            val audioB64 = resp?.optString("audio_base64", "") ?: ""
                            if (audioB64.isNotEmpty()) {
                                val audioBytes = android.util.Base64.decode(audioB64, android.util.Base64.DEFAULT)
                                audioHelper.playAudio(audioBytes)
                            }
                        }
                    } catch (e: Exception) {
                        e.printStackTrace()
                    } finally {
                        updateNotification("Conectado con Jota (PC) [Wake Word activo]")
                        wakeWordDetector?.startListening()
                    }
                }
            }
        })
        wakeWordDetector?.startListening()
    }

    override fun onDestroy() {
        stopAlarm()
        wakeWordDetector?.stopListening()
        clipboardDebounceJob?.cancel()
        clipboardListener?.let {
            val cm = getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
            cm?.removePrimaryClipChangedListener(it)
        }
        serviceScope.cancel()
        bridgeClient?.disconnect()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
