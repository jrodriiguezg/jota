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

    private var mediaSession: android.media.session.MediaSession? = null
    private var localMediaPlayer: android.media.MediaPlayer? = null

    private var lastSyncedClipboard: String = ""
    private var clipboardListener: ClipboardManager.OnPrimaryClipChangedListener? = null
    private var clipboardDebounceJob: Job? = null

    companion object {
        const val CHANNEL_ID = "jota_bridge_channel"
        const val MEDIA_CHANNEL_ID = "jota_media_channel"
        const val NOTIFICATION_ID = 1001
        const val MEDIA_NOTIFICATION_ID = 1002
        const val ACTION_STOP_ALARM = "com.jota.link.STOP_ALARM"
        const val ACTION_TOGGLE_WAKE_WORD = "com.jota.link.TOGGLE_WAKE_WORD"
        const val ACTION_MEDIA_PLAY_PAUSE = "com.jota.link.MEDIA_PLAY_PAUSE"
        const val ACTION_MEDIA_NEXT = "com.jota.link.MEDIA_NEXT"
        const val ACTION_MEDIA_PREV = "com.jota.link.MEDIA_PREV"
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        initMediaSession()
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

    private fun initMediaSession() {
        mediaSession = android.media.session.MediaSession(this, "JotaLinkMedia").apply {
            setCallback(object : android.media.session.MediaSession.Callback() {
                override fun onPlay() {
                    if (localMediaPlayer != null && !localMediaPlayer!!.isPlaying) {
                        localMediaPlayer?.start()
                        updateLocalPlaybackState(true)
                    } else {
                        serviceScope.launch { bridgeClient?.executePcAction("play") }
                    }
                }

                override fun onPause() {
                    if (localMediaPlayer != null && localMediaPlayer!!.isPlaying) {
                        localMediaPlayer?.pause()
                        updateLocalPlaybackState(false)
                    } else {
                        serviceScope.launch { bridgeClient?.executePcAction("pause") }
                    }
                }

                override fun onSkipToNext() {
                    serviceScope.launch { bridgeClient?.executePcAction("next") }
                }

                override fun onSkipToPrevious() {
                    serviceScope.launch { bridgeClient?.executePcAction("previous") }
                }
            })
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

        if (intent?.action == ACTION_MEDIA_PLAY_PAUSE) {
            if (localMediaPlayer != null) {
                if (localMediaPlayer!!.isPlaying) {
                    localMediaPlayer?.pause()
                    updateLocalPlaybackState(false)
                } else {
                    localMediaPlayer?.start()
                    updateLocalPlaybackState(true)
                }
            } else {
                serviceScope.launch { bridgeClient?.executePcAction("play_pause") }
            }
            return START_STICKY
        }

        if (intent?.action == ACTION_MEDIA_NEXT) {
            serviceScope.launch { bridgeClient?.executePcAction("next") }
            return START_STICKY
        }

        if (intent?.action == ACTION_MEDIA_PREV) {
            serviceScope.launch { bridgeClient?.executePcAction("previous") }
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

    override fun onPcMediaUpdate(mediaData: org.json.JSONObject) {
        val status = mediaData.optString("status", "")
        val title = mediaData.optString("title", "")
        val artist = mediaData.optString("artist", "")
        val album = mediaData.optString("album", "")
        val isPlaying = status.equals("Playing", ignoreCase = true)
        val isPaused = status.equals("Paused", ignoreCase = true)

        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if ((!isPlaying && !isPaused) || title.isEmpty()) {
            mediaSession?.isActive = false
            nm.cancel(MEDIA_NOTIFICATION_ID)
            return
        }

        mediaSession?.setMetadata(
            android.media.MediaMetadata.Builder()
                .putString(android.media.MediaMetadata.METADATA_KEY_TITLE, title)
                .putString(android.media.MediaMetadata.METADATA_KEY_ARTIST, artist)
                .putString(android.media.MediaMetadata.METADATA_KEY_ALBUM, album)
                .build()
        )

        val state = if (isPlaying) android.media.session.PlaybackState.STATE_PLAYING else android.media.session.PlaybackState.STATE_PAUSED
        val actions = android.media.session.PlaybackState.ACTION_PLAY or
            android.media.session.PlaybackState.ACTION_PAUSE or
            android.media.session.PlaybackState.ACTION_PLAY_PAUSE or
            android.media.session.PlaybackState.ACTION_SKIP_TO_NEXT or
            android.media.session.PlaybackState.ACTION_SKIP_TO_PREVIOUS

        mediaSession?.setPlaybackState(
            android.media.session.PlaybackState.Builder()
                .setActions(actions)
                .setState(state, android.media.session.PlaybackState.PLAYBACK_POSITION_UNKNOWN, 1.0f)
                .build()
        )
        mediaSession?.isActive = true

        val prevIntent = PendingIntent.getService(
            this, 1,
            Intent(this, JotaBridgeService::class.java).apply { action = ACTION_MEDIA_PREV },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val playPauseIntent = PendingIntent.getService(
            this, 2,
            Intent(this, JotaBridgeService::class.java).apply { action = ACTION_MEDIA_PLAY_PAUSE },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val nextIntent = PendingIntent.getService(
            this, 3,
            Intent(this, JotaBridgeService::class.java).apply { action = ACTION_MEDIA_NEXT },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val iconPlayPause = if (isPlaying) {
            android.R.drawable.ic_media_pause
        } else {
            android.R.drawable.ic_media_play
        }

        @Suppress("DEPRECATION")
        val notifBuilder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, MEDIA_CHANNEL_ID)
        } else {
            Notification.Builder(this)
        }

        val mediaStyle = Notification.MediaStyle()
            .setMediaSession(mediaSession?.sessionToken)
            .setShowActionsInCompactView(0, 1, 2)

        val notif = notifBuilder
            .setContentTitle(title)
            .setContentText(if (artist.isNotEmpty()) "$artist • En el PC" else "Reproduciendo en PC")
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setStyle(mediaStyle)
            .addAction(Notification.Action.Builder(android.R.drawable.ic_media_previous, "Anterior", prevIntent).build())
            .addAction(Notification.Action.Builder(iconPlayPause, "Play/Pausa", playPauseIntent).build())
            .addAction(Notification.Action.Builder(android.R.drawable.ic_media_next, "Siguiente", nextIntent).build())
            .setOngoing(isPlaying)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .build()

        nm.notify(MEDIA_NOTIFICATION_ID, notif)
    }

    override fun onMediaHandoff(handoffData: org.json.JSONObject) {
        val title = handoffData.optString("title", "Canción")
        val artist = handoffData.optString("artist", "")
        val streamUrl = handoffData.optString("stream_url", "")
        val positionMs = handoffData.optInt("position_ms", 0)

        Handler(Looper.getMainLooper()).post {
            android.widget.Toast.makeText(
                applicationContext,
                "Reproduccion transferida al movil: $title",
                android.widget.Toast.LENGTH_LONG
            ).show()
        }

        if (streamUrl.isNotEmpty()) {
            try {
                localMediaPlayer?.release()
                localMediaPlayer = android.media.MediaPlayer().apply {
                    setAudioAttributes(
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_MEDIA)
                            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                            .build()
                    )
                    setDataSource(streamUrl)
                    setOnPreparedListener { mp ->
                        if (positionMs > 0) {
                            mp.seekTo(positionMs)
                        }
                        mp.start()
                        updateLocalPlaybackState(true, title, artist)
                    }
                    setOnCompletionListener {
                        updateLocalPlaybackState(false)
                    }
                    prepareAsync()
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    private fun updateLocalPlaybackState(isPlaying: Boolean, title: String = "", artist: String = "") {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (title.isNotEmpty()) {
            mediaSession?.setMetadata(
                android.media.MediaMetadata.Builder()
                    .putString(android.media.MediaMetadata.METADATA_KEY_TITLE, title)
                    .putString(android.media.MediaMetadata.METADATA_KEY_ARTIST, artist)
                    .build()
            )
        }
        val state = if (isPlaying) android.media.session.PlaybackState.STATE_PLAYING else android.media.session.PlaybackState.STATE_PAUSED
        mediaSession?.setPlaybackState(
            android.media.session.PlaybackState.Builder()
                .setActions(android.media.session.PlaybackState.ACTION_PLAY or android.media.session.PlaybackState.ACTION_PAUSE or android.media.session.PlaybackState.ACTION_PLAY_PAUSE)
                .setState(state, android.media.session.PlaybackState.PLAYBACK_POSITION_UNKNOWN, 1.0f)
                .build()
        )
        mediaSession?.isActive = isPlaying
        if (!isPlaying && localMediaPlayer == null) {
            nm.cancel(MEDIA_NOTIFICATION_ID)
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NotificationManager::class.java)
            val serviceChannel = NotificationChannel(
                CHANNEL_ID,
                "Jota Bridge Service",
                NotificationManager.IMPORTANCE_LOW
            )
            val mediaChannel = NotificationChannel(
                MEDIA_CHANNEL_ID,
                "Multimedia Jota",
                NotificationManager.IMPORTANCE_LOW
            )
            nm.createNotificationChannel(serviceChannel)
            nm.createNotificationChannel(mediaChannel)
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
        mediaSession?.release()
        localMediaPlayer?.release()
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
