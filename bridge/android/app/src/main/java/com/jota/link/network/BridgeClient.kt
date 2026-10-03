package com.jota.link.network

import android.content.Context
import android.os.BatteryManager
import kotlinx.coroutines.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.TimeUnit

class BridgeClient(
    private val context: Context,
    private val baseUrl: String,
    private val apiKey: String,
    private val deviceId: String
) {
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private var isConnected = false

    interface BridgeListener {
        fun onConnected()
        fun onDisconnected()
        fun onRing(durationSeconds: Int)
        fun onClipboardReceived(text: String)
        fun onOpenUrl(url: String)
    }

    var listener: BridgeListener? = null

    fun connectWebSocket() {
        val wsBaseUrl = baseUrl.replace("http://", "ws://").replace("https://", "wss://")
        val wsUrl = "$wsBaseUrl/ws/phone?token=$apiKey&device_id=$deviceId&model=Android_${android.os.Build.MODEL}"

        val request = Request.Builder()
            .url(wsUrl)
            .build()

        webSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                isConnected = true
                listener?.onConnected()
                sendBatteryStatus()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    val event = json.optString("event")
                    val payload = json.optJSONObject("payload") ?: JSONObject()

                    when (event) {
                        "ring" -> {
                            val duration = payload.optInt("duration_seconds", 15)
                            listener?.onRing(duration)
                        }
                        "clipboard" -> {
                            val clipText = payload.optString("text")
                            listener?.onClipboardReceived(clipText)
                        }
                        "open_url" -> {
                            val targetUrl = payload.optString("url")
                            listener?.onOpenUrl(targetUrl)
                        }
                    }
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                isConnected = false
                listener?.onDisconnected()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                isConnected = false
                listener?.onDisconnected()
            }
        })
    }

    fun sendBatteryStatus() {
        val bm = context.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager
        val batteryPct = bm?.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY) ?: -1

        val payload = JSONObject().apply {
            put("event", "status_update")
            put("payload", JSONObject().apply {
                put("battery", batteryPct)
                put("model", android.os.Build.MODEL)
            })
        }
        webSocket?.send(payload.toString())
    }

    suspend fun askVoice(wavAudioBytes: ByteArray, generateAudio: Boolean = true): JSONObject = withContext(Dispatchers.IO) {
        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("generate_audio", generateAudio.toString())
            .addFormDataPart(
                "file",
                "voice.wav",
                wavAudioBytes.toRequestBody("audio/wav".toMediaType())
            )
            .build()

        val request = Request.Builder()
            .url("$baseUrl/api/v1/voice/ask")
            .header("X-Bridge-Key", apiKey)
            .post(requestBody)
            .build()

        val response = httpClient.newCall(request).execute()
        val bodyStr = response.body?.string() ?: "{}"
        JSONObject(bodyStr)
    }

    suspend fun askText(prompt: String): JSONObject = withContext(Dispatchers.IO) {
        val json = JSONObject().apply {
            put("prompt", prompt)
            put("generate_audio", false)
        }
        val request = Request.Builder()
            .url("$baseUrl/api/v1/text/ask")
            .header("X-Bridge-Key", apiKey)
            .post(json.toString().toRequestBody("application/json".toMediaType()))
            .build()

        val response = httpClient.newCall(request).execute()
        val bodyStr = response.body?.string() ?: "{}"
        JSONObject(bodyStr)
    }

    suspend fun getPcStatus(): JSONObject = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/pc/status")
            .header("X-Bridge-Key", apiKey)
            .get()
            .build()

        val response = httpClient.newCall(request).execute()
        val bodyStr = response.body?.string() ?: "{}"
        JSONObject(bodyStr)
    }

    suspend fun getPcScreenshot(): ByteArray = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/pc/screenshot")
            .header("X-Bridge-Key", apiKey)
            .get()
            .build()

        val response = httpClient.newCall(request).execute()
        response.body?.bytes() ?: ByteArray(0)
    }

    suspend fun getPcClipboard(): String = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/pc/clipboard")
            .header("X-Bridge-Key", apiKey)
            .get()
            .build()

        val response = httpClient.newCall(request).execute()
        val bodyStr = response.body?.string() ?: "{}"
        JSONObject(bodyStr).optString("text", "")
    }

    suspend fun setPcClipboard(text: String): Boolean = withContext(Dispatchers.IO) {
        val json = JSONObject().apply { put("text", text) }
        val request = Request.Builder()
            .url("$baseUrl/api/v1/pc/clipboard")
            .header("X-Bridge-Key", apiKey)
            .post(json.toString().toRequestBody("application/json".toMediaType()))
            .build()

        val response = httpClient.newCall(request).execute()
        response.isSuccessful
    }

    suspend fun downloadPcFile(remotePath: String, destFile: File): Boolean = withContext(Dispatchers.IO) {
        val url = "$baseUrl/api/v1/pc/file?path=${java.net.URLEncoder.encode(remotePath, "UTF-8")}"
        val request = Request.Builder()
            .url(url)
            .header("X-Bridge-Key", apiKey)
            .get()
            .build()

        val response = httpClient.newCall(request).execute()
        if (response.isSuccessful && response.body != null) {
            FileOutputStream(destFile).use { out ->
                response.body!!.byteStream().copyTo(out)
            }
            true
        } else {
            false
        }
    }

    fun disconnect() {
        webSocket?.close(1000, "App closed")
        webSocket = null
        isConnected = false
    }
}
