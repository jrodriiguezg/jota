package com.jota.link.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import android.widget.Toast
import com.jota.link.R
import com.jota.link.network.BridgeClient
import com.jota.link.ui.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class JotaWidgetProvider : AppWidgetProvider() {

    companion object {
        const val ACTION_LOCK = "com.jota.link.WIDGET_ACTION_LOCK"
        const val ACTION_PLAY_PAUSE = "com.jota.link.WIDGET_ACTION_PLAY_PAUSE"
        const val ACTION_MUTE = "com.jota.link.WIDGET_ACTION_MUTE"
    }

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        for (appWidgetId in appWidgetIds) {
            updateAppWidget(context, appWidgetManager, appWidgetId)
        }
    }

    private fun updateAppWidget(context: Context, appWidgetManager: AppWidgetManager, appWidgetId: Int) {
        val views = RemoteViews(context.packageName, R.layout.widget_jota)

        // 1. Abrir la app al pulsar "Hablar"
        val voiceIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("auto_voice", true)
        }
        val voicePending = PendingIntent.getActivity(
            context, 101, voiceIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        views.setOnClickPendingIntent(R.id.btn_widget_voice, voicePending)

        // 2. Play / Pausa PC
        val playIntent = Intent(context, JotaWidgetProvider::class.java).apply { action = ACTION_PLAY_PAUSE }
        val playPending = PendingIntent.getBroadcast(
            context, 102, playIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        views.setOnClickPendingIntent(R.id.btn_widget_play, playPending)

        // 3. Silenciar PC
        val muteIntent = Intent(context, JotaWidgetProvider::class.java).apply { action = ACTION_MUTE }
        val mutePending = PendingIntent.getBroadcast(
            context, 103, muteIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        views.setOnClickPendingIntent(R.id.btn_widget_mute, mutePending)

        // 4. Bloquear PC
        val lockIntent = Intent(context, JotaWidgetProvider::class.java).apply { action = ACTION_LOCK }
        val lockPending = PendingIntent.getBroadcast(
            context, 104, lockIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        views.setOnClickPendingIntent(R.id.btn_widget_lock, lockPending)

        appWidgetManager.updateAppWidget(appWidgetId, views)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)

        val actionToExecute = when (intent.action) {
            ACTION_LOCK -> "lock"
            ACTION_PLAY_PAUSE -> "play_pause"
            ACTION_MUTE -> "mute"
            else -> null
        }

        if (actionToExecute != null) {
            val prefs = context.getSharedPreferences("jota_link_prefs", Context.MODE_PRIVATE)
            val serverUrl = prefs.getString("server_url", "http://100.81.222.82:8765") ?: "http://100.81.222.82:8765"
            val apiKey = prefs.getString("api_key", "jota-secret-tailscale-key") ?: "jota-secret-tailscale-key"
            val deviceId = prefs.getString("device_id", "android_widget") ?: "android_widget"

            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val client = BridgeClient(context, serverUrl, apiKey, deviceId)
                    val (ok, msg) = client.executePcAction(actionToExecute)
                    CoroutineScope(Dispatchers.Main).launch {
                        Toast.makeText(context, if (ok) msg else "Error: $msg", Toast.LENGTH_SHORT).show()
                    }
                } catch (e: Exception) {
                    CoroutineScope(Dispatchers.Main).launch {
                        Toast.makeText(context, "Fallo al conectar con el PC: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }
    }
}
