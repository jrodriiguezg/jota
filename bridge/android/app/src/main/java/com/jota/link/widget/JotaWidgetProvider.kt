package com.jota.link.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import com.jota.link.R
import com.jota.link.network.BridgeClient
import com.jota.link.ui.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class JotaWidgetProvider : AppWidgetProvider() {

    companion object {
        const val ACTION_WIDGET_LOCK = "com.jota.link.WIDGET_LOCK"
        const val ACTION_WIDGET_MEDIA = "com.jota.link.WIDGET_MEDIA"

        fun updateWidgetViews(context: Context, appWidgetManager: AppWidgetManager, appWidgetId: Int) {
            val views = RemoteViews(context.packageName, R.layout.widget_jota_glance)

            // Intent para hablar con Jota
            val voiceIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("EXTRA_START_VOICE", true)
            }
            val voicePending = PendingIntent.getActivity(
                context,
                101,
                voiceIntent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            views.setOnClickPendingIntent(R.id.btn_widget_voice, voicePending)

            // Intent para bloquear PC
            val lockIntent = Intent(context, JotaWidgetProvider::class.java).apply {
                action = ACTION_WIDGET_LOCK
            }
            val lockPending = PendingIntent.getBroadcast(
                context,
                102,
                lockIntent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            views.setOnClickPendingIntent(R.id.btn_widget_lock, lockPending)

            // Intent para pausar/reanudar musica
            val mediaIntent = Intent(context, JotaWidgetProvider::class.java).apply {
                action = ACTION_WIDGET_MEDIA
            }
            val mediaPending = PendingIntent.getBroadcast(
                context,
                103,
                mediaIntent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            views.setOnClickPendingIntent(R.id.btn_widget_media, mediaPending)

            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        for (appWidgetId in appWidgetIds) {
            updateWidgetViews(context, appWidgetManager, appWidgetId)
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        val action = intent.action ?: return
        val prefs = context.getSharedPreferences("jota_link_prefs", Context.MODE_PRIVATE)
        val serverUrl = prefs.getString("server_url", "http://100.81.222.82:8765") ?: "http://100.81.222.82:8765"
        val apiKey = prefs.getString("api_key", "jota-secret-tailscale-key") ?: "jota-secret-tailscale-key"

        val scope = CoroutineScope(Dispatchers.IO)
        if (action == ACTION_WIDGET_LOCK) {
            scope.launch {
                try {
                    val client = BridgeClient(context, serverUrl, apiKey, "widget_client")
                    client.executePcAction("lock")
                } catch (_: Exception) {}
            }
        } else if (action == ACTION_WIDGET_MEDIA) {
            scope.launch {
                try {
                    val client = BridgeClient(context, serverUrl, apiKey, "widget_client")
                    client.executePcAction("play_pause")
                } catch (_: Exception) {}
            }
        }
    }
}
