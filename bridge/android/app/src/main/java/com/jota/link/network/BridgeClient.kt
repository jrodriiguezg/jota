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
        fun onTorch(enabled: Boolean)
        fun onSilent(silent: Boolean)
        fun onReceiveFile(filename: String, remotePath: String, sizeBytes: Long)
        fun onPcNotification(title: String, message: String) {}
        fun onPcMediaUpdate(mediaData: JSONObject) {}
        fun onMediaHandoff(handoffData: JSONObject) {}
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
                        "connected" -> {
                            val pcStatus = json.optJSONObject("pc_status")
                            val media = pcStatus?.optJSONObject("media")
                            if (media != null) {
                                listener?.onPcMediaUpdate(media)
                            }
                        }
                        "pc_status" -> {
                            val media = payload.optJSONObject("media")
                            if (media != null) {
                                listener?.onPcMediaUpdate(media)
                            }
                        }
                        "pc_media" -> {
                            listener?.onPcMediaUpdate(payload)
                        }
                        "media_handoff" -> {
                            listener?.onMediaHandoff(payload)
                        }
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
                        "torch" -> {
                            val enabled = payload.optBoolean("enabled", true)
                            listener?.onTorch(enabled)
                        }
                        "silent" -> {
                            val silent = payload.optBoolean("silent", true)
                            listener?.onSilent(silent)
                        }
                        "receive_file" -> {
                            val filename = payload.optString("filename", "archivo_jota")
                            val remotePath = payload.optString("remote_path", filename)
                            val sizeBytes = payload.optLong("size_bytes", 0L)
                            listener?.onReceiveFile(filename, remotePath, sizeBytes)
                        }
                        "pc_notification" -> {
                            val title = payload.optString("title", "Jota (PC)")
                            val message = payload.optString("message", "")
                            listener?.onPcNotification(title, message)
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

        var isCharging = false
        try {
            val ifilter = android.content.IntentFilter(android.content.Intent.ACTION_BATTERY_CHANGED)
            val batteryStatus: android.content.Intent? = context.registerReceiver(null, ifilter)
            val status: Int = batteryStatus?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
            isCharging = status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL
        } catch (_: Exception) {}

        val payload = JSONObject().apply {
            put("event", "status_update")
            put("payload", JSONObject().apply {
                put("battery", batteryPct)
                put("is_charging", isCharging)
                put("model", android.os.Build.MODEL)
            })
        }
        webSocket?.send(payload.toString())
    }

    suspend fun askVoice(
        wavAudioBytes: ByteArray,
        generateAudio: Boolean = true,
        playOnPc: Boolean = true
    ): JSONObject = withContext(Dispatchers.IO) {
        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("generate_audio", generateAudio.toString())
            .addFormDataPart("play_on_pc", playOnPc.toString())
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

    suspend fun askText(
        prompt: String,
        generateAudio: Boolean = true,
        playOnPc: Boolean = true
    ): JSONObject = withContext(Dispatchers.IO) {
        val json = JSONObject().apply {
            put("prompt", prompt)
            put("generate_audio", generateAudio)
            put("play_on_pc", playOnPc)
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

    suspend fun downloadAudio(audioId: String): ByteArray = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/audio/$audioId")
            .header("X-Bridge-Key", apiKey)
            .get()
            .build()

        val response = httpClient.newCall(request).execute()
        response.body?.bytes() ?: ByteArray(0)
    }

    suspend fun executePcAction(action: String): Pair<Boolean, String> = withContext(Dispatchers.IO) {
        // Envio directo y de baja latencia por WebSocket si la conexion esta activa
        if (isConnected && webSocket != null) {
            val json = JSONObject().apply {
                put("event", "pc_action")
                put("payload", JSONObject().apply { put("action", action) })
            }
            val sent = webSocket?.send(json.toString()) ?: false
            if (sent) {
                return@withContext Pair(true, "Comando enviado via WebSocket")
            }
        }

        // Fallback HTTP
        val json = JSONObject().apply { put("action", action) }
        val request = Request.Builder()
            .url("$baseUrl/api/v1/pc/action")
            .header("X-Bridge-Key", apiKey)
            .post(json.toString().toRequestBody("application/json".toMediaType()))
            .build()

        val response = httpClient.newCall(request).execute()
        val bodyStr = response.body?.string() ?: "{}"
        val respJson = JSONObject(bodyStr)
        val msg = respJson.optString("message", respJson.optString("detail", "Error"))
        Pair(response.isSuccessful, msg)
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

    suspend fun getPcScreenshot(
        format: String = "jpeg",
        quality: Int = 75,
        scale: Float = 0.8f
    ): ByteArray = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/pc/screenshot?format=$format&quality=$quality&scale=$scale")
            .header("X-Bridge-Key", apiKey)
            .get()
            .build()

        val response = httpClient.newCall(request).execute()
        response.body?.bytes() ?: ByteArray(0)
    }

    suspend fun getPcScreenshots(): List<JSONObject> = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/pc/screenshots")
            .header("X-Bridge-Key", apiKey)
            .get()
            .build()

        val response = httpClient.newCall(request).execute()
        val bodyStr = response.body?.string() ?: "{}"
        val json = JSONObject(bodyStr)
        val array = json.optJSONArray("screenshots") ?: org.json.JSONArray()
        val list = mutableListOf<JSONObject>()
        for (i in 0 until array.length()) {
            list.add(array.getJSONObject(i))
        }
        list
    }

    suspend fun getScreenshotBytes(nameOrPath: String): ByteArray = withContext(Dispatchers.IO) {
        val encoded = java.net.URLEncoder.encode(nameOrPath, "UTF-8")
        val request = Request.Builder()
            .url("$baseUrl/api/v1/pc/screenshots/file?name=$encoded")
            .header("X-Bridge-Key", apiKey)
            .get()
            .build()

        val response = httpClient.newCall(request).execute()
        response.body?.bytes() ?: ByteArray(0)
    }

    suspend fun captureNewScreenshot(): List<JSONObject> = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/pc/screenshots/capture")
            .header("X-Bridge-Key", apiKey)
            .post("{}".toRequestBody("application/json".toMediaType()))
            .build()

        val response = httpClient.newCall(request).execute()
        val bodyStr = response.body?.string() ?: "{}"
        val json = JSONObject(bodyStr)
        val array = json.optJSONArray("screenshots") ?: org.json.JSONArray()
        val list = mutableListOf<JSONObject>()
        for (i in 0 until array.length()) {
            list.add(array.getJSONObject(i))
        }
        list
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

    fun sendClipboard(text: String): Boolean {
        if (!isConnected || webSocket == null) return false
        val json = JSONObject().apply {
            put("event", "clipboard")
            put("payload", JSONObject().apply {
                put("text", text)
            })
        }
        return webSocket?.send(json.toString()) ?: false
    }

    suspend fun getPcNetworkInfo(): JSONObject = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("$baseUrl/api/v1/pc/network")
                .header("X-Bridge-Key", apiKey)
                .get()
                .build()
            val response = httpClient.newCall(request).execute()
            val bodyStr = response.body?.string() ?: "{}"
            JSONObject(bodyStr)
        } catch (e: Exception) {
            JSONObject()
        }
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

    suspend fun uploadFileToPc(filename: String, fileBytes: ByteArray): Pair<Boolean, String> = withContext(Dispatchers.IO) {
        try {
            val requestBody = MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart(
                    "file",
                    filename,
                    fileBytes.toRequestBody("application/octet-stream".toMediaType())
                )
                .build()

            val request = Request.Builder()
                .url("$baseUrl/api/v1/pc/upload")
                .header("X-Bridge-Key", apiKey)
                .post(requestBody)
                .build()

            val response = httpClient.newCall(request).execute()
            if (response.isSuccessful) {
                Pair(true, "Archivo enviado al PC con exito")
            } else {
                Pair(false, "Error del servidor: ${response.code}")
            }
        } catch (e: Exception) {
            Pair(false, e.message ?: "Fallo de red al enviar archivo")
        }
    }

    suspend fun openUrlOnPc(url: String): Pair<Boolean, String> = withContext(Dispatchers.IO) {
        executePcAction("open_url:$url")
    }

    fun disconnect() {
        webSocket?.close(1000, "App closed")
        webSocket = null
        isConnected = false
    }
}
