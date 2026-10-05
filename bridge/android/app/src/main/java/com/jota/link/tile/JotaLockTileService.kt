package com.jota.link.tile

import android.content.Context
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import android.widget.Toast
import com.jota.link.network.BridgeClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class JotaLockTileService : TileService() {
    private val scope = CoroutineScope(Dispatchers.IO)

    override fun onStartListening() {
        super.onStartListening()
        qsTile?.apply {
            state = Tile.STATE_INACTIVE
            label = "Bloquear PC"
            updateTile()
        }
    }

    override fun onClick() {
        super.onClick()
        val prefs = getSharedPreferences("jota_link_prefs", Context.MODE_PRIVATE)
        val serverUrl = prefs.getString("server_url", "http://100.81.222.82:8765") ?: "http://100.81.222.82:8765"
        val apiKey = prefs.getString("api_key", "jota-secret-tailscale-key") ?: "jota-secret-tailscale-key"

        vibrateClick()

        scope.launch {
            try {
                val client = BridgeClient(applicationContext, serverUrl, apiKey, "tile_locker")
                val (ok, _) = client.executePcAction("lock")
                launch(Dispatchers.Main) {
                    if (ok) {
                        Toast.makeText(applicationContext, "PC bloqueado", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(applicationContext, "No se pudo bloquear el PC", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                launch(Dispatchers.Main) {
                    Toast.makeText(applicationContext, "Error al comunicar con PC", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun vibrateClick() {
        try {
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                val vm = getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
                vm?.defaultVibrator?.vibrate(VibrationEffect.createOneShot(50, VibrationEffect.DEFAULT_AMPLITUDE))
            } else {
                @Suppress("DEPRECATION")
                val v = getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
                @Suppress("DEPRECATION")
                v?.vibrate(50)
            }
        } catch (_: Exception) {}
    }
}
