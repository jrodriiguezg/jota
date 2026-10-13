package com.jota.link.ui

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.util.Base64
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.*
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.jota.link.R
import com.jota.link.audio.AudioHelper
import com.jota.link.network.BridgeClient
import com.jota.link.network.JotaDiscoveryManager
import com.jota.link.network.WakeOnLan
import com.jota.link.service.JotaBridgeService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

data class ChatMessageItem(
    val id: Long = System.currentTimeMillis(),
    val sender: String,
    val text: String,
    val time: String,
    val audioBytes: ByteArray? = null
)

data class ClusterNode(
    val nodeId: String,
    val name: String,
    val mode: String,
    val hardwareFingerprint: String,
    val ipAddress: String,
    val port: Int,
    val status: String,
    val isGpuWorker: Boolean,
    val gpuInfo: String,
    val hostname: String,
    val os: String,
    val arch: String,
    val macPrimary: String
)

data class ClusterContainer(
    val name: String,
    val status: String,
    val image: String,
    val engine: String,
    val nodeName: String,
    val nodeIp: String
)

class MainActivity : ComponentActivity() {
    private val audioHelper = AudioHelper()
    private var bridgeClient: BridgeClient? = null
    private lateinit var prefs: SharedPreferences

    private var serverUrl by mutableStateOf("http://100.85.176.113:8765")
    private var serverFallbackUrl by mutableStateOf("http://192.168.1.135:8765")
    private var apiKey by mutableStateOf("jota-secret-tailscale-key")
    private var deviceId by mutableStateOf("android_user")

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        if (permissions[Manifest.permission.RECORD_AUDIO] == true) {
            startBridgeService()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = getSharedPreferences("jota_link_prefs", Context.MODE_PRIVATE)

        serverUrl = prefs.getString("server_url", "http://100.85.176.113:8765") ?: "http://100.85.176.113:8765"
        serverFallbackUrl = prefs.getString("server_fallback_url", "http://192.168.1.135:8765") ?: "http://192.168.1.135:8765"
        apiKey = prefs.getString("api_key", "jota-secret-tailscale-key") ?: "jota-secret-tailscale-key"
        deviceId = prefs.getString("device_id", "android_user") ?: "android_user"

        bridgeClient = BridgeClient(this, serverUrl, apiKey, deviceId, serverFallbackUrl)

        checkPermissions()
        handleIncomingIntent(intent)

        setContent {
            MaterialTheme(
                colorScheme = darkColorScheme(
                    primary = Color(0xFFA8C7FA),
                    onPrimary = Color(0xFF062E6F),
                    primaryContainer = Color(0xFF1E3A5F),
                    onPrimaryContainer = Color(0xFFD3E3FD),
                    secondary = Color(0xFF7FCFFF),
                    onSecondary = Color(0xFF003548),
                    secondaryContainer = Color(0xFF1E3542),
                    onSecondaryContainer = Color(0xFFC2E7FF),
                    tertiary = Color(0xFF80CBC4),
                    background = Color(0xFF0C1017),
                    onBackground = Color(0xFFE1E3EB),
                    surface = Color(0xFF111722),
                    onSurface = Color(0xFFE1E3EB),
                    surfaceVariant = Color(0xFF1A2330),
                    onSurfaceVariant = Color(0xFFC3C7D2),
                    outline = Color(0xFF2C394A),
                    outlineVariant = Color(0xFF1F2937),
                    error = Color(0xFFF2B8B5),
                    onError = Color(0xFF601410)
                )
            ) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    JotaLinkScreen()
                }
            }
        }
    }

    private fun checkPermissions() {
        val perms = arrayOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.POST_NOTIFICATIONS
        )
        val missing = perms.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            requestPermissionLauncher.launch(missing.toTypedArray())
        } else {
            startBridgeService()
        }
    }

    private fun startBridgeService(enableWakeWord: Boolean? = null) {
        val wakeWordPref = enableWakeWord ?: prefs.getBoolean("enable_wake_word", false)
        val intent = Intent(this, JotaBridgeService::class.java).apply {
            putExtra("baseUrl", serverUrl)
            putExtra("fallbackUrl", serverFallbackUrl)
            putExtra("apiKey", apiKey)
            putExtra("deviceId", deviceId)
            putExtra("enableWakeWord", wakeWordPref)
        }
        startForegroundService(intent)
    }

    private fun updateConnectionConfig(
        newUrl: String,
        newKey: String,
        newId: String,
        newFallbackUrl: String? = null,
        newMac: String? = null
    ) {
        serverUrl = newUrl.trim()
        if (!newFallbackUrl.isNullOrBlank()) {
            serverFallbackUrl = newFallbackUrl.trim()
        }
        apiKey = newKey.trim()
        deviceId = newId.trim()

        prefs.edit().apply {
            putString("server_url", serverUrl)
            putString("server_fallback_url", serverFallbackUrl)
            putString("api_key", apiKey)
            putString("device_id", deviceId)
            if (!newMac.isNullOrBlank()) {
                putString("pc_mac", newMac.trim())
            }
            apply()
        }

        bridgeClient?.disconnect()
        bridgeClient = BridgeClient(this, serverUrl, apiKey, deviceId, serverFallbackUrl)
        startBridgeService()

        if (newMac.isNullOrBlank()) {
            lifecycleScope.launch(Dispatchers.IO) {
                try {
                    val net = bridgeClient?.getPcNetworkInfo()
                    val mac = net?.optString("primary_mac", "") ?: ""
                    if (mac.isNotEmpty()) {
                        prefs.edit().putString("pc_mac", mac).apply()
                    }
                } catch (_: Exception) {}
            }
        }

        Toast.makeText(this, "Ajustes guardados. Reconectando...", Toast.LENGTH_SHORT).show()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIncomingIntent(intent)
    }

    private fun handleIncomingIntent(intent: Intent?) {
        if (intent == null) return
        if (intent.getBooleanExtra("EXTRA_START_VOICE", false)) {
            Toast.makeText(this, "Modo de voz activado desde acceso rapido", Toast.LENGTH_SHORT).show()
        }
        val action = intent.action

        if (Intent.ACTION_SEND == action) {
            val text = intent.getStringExtra(Intent.EXTRA_TEXT)
            if (!text.isNullOrBlank()) {
                handleSharedText(text.trim())
            }
            @Suppress("DEPRECATION")
            val uri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
            if (uri != null) {
                handleSharedUri(uri)
            }
        } else if (Intent.ACTION_SEND_MULTIPLE == action) {
            @Suppress("DEPRECATION")
            val uris = intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)
            uris?.forEach { uri ->
                handleSharedUri(uri)
            }
        }
    }

    private fun handleSharedText(text: String) {
        lifecycleScope.launch(Dispatchers.IO) {
            val client = bridgeClient ?: BridgeClient(this@MainActivity, serverUrl, apiKey, deviceId, serverFallbackUrl)
            val isUrl = text.startsWith("http://") || text.startsWith("https://")
            if (isUrl) {
                val (resUrl, msgUrl) = client.openUrlOnPc(text)
                client.setPcClipboard(text)
                withContext(Dispatchers.Main) {
                    if (resUrl) {
                        Toast.makeText(this@MainActivity, "Enlace abierto en el PC", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this@MainActivity, "Error al abrir enlace: $msgUrl", Toast.LENGTH_SHORT).show()
                    }
                }
            } else {
                val resClip = client.setPcClipboard(text)
                withContext(Dispatchers.Main) {
                    if (resClip) {
                        Toast.makeText(this@MainActivity, "Texto copiado al portapapeles del PC", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this@MainActivity, "Error enviando texto al PC", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }
    }

    private fun handleSharedUri(uri: Uri) {
        lifecycleScope.launch(Dispatchers.IO) {
            val client = bridgeClient ?: BridgeClient(this@MainActivity, serverUrl, apiKey, deviceId, serverFallbackUrl)
            var fileName = "archivo_compartido_${System.currentTimeMillis()}"
            try {
                contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                    val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (nameIndex != -1 && cursor.moveToFirst()) {
                        val name = cursor.getString(nameIndex)
                        if (!name.isNullOrBlank()) {
                            fileName = name
                        }
                    }
                }
            } catch (_: Exception) {}

            try {
                val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() }
                if (bytes != null && bytes.isNotEmpty()) {
                    val (ok, msg) = client.uploadFileToPc(fileName, bytes)
                    withContext(Dispatchers.Main) {
                        if (ok) {
                            Toast.makeText(this@MainActivity, "Enviado al PC: $fileName", Toast.LENGTH_SHORT).show()
                        } else {
                            Toast.makeText(this@MainActivity, "Error enviando archivo: $msg", Toast.LENGTH_SHORT).show()
                        }
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "Error leyendo archivo: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun parseClusterData(json: JSONObject?): Triple<List<ClusterNode>, List<ClusterContainer>, Boolean> {
        if (json == null) return Triple(emptyList(), emptyList(), false)
        val nodesList = mutableListOf<ClusterNode>()
        val containersList = mutableListOf<ClusterContainer>()

        val nodesArr = json.optJSONArray("nodes")
        if (nodesArr != null) {
            for (i in 0 until nodesArr.length()) {
                val obj = nodesArr.optJSONObject(i) ?: continue
                val meta = obj.optJSONObject("metadata")
                val isGpu = obj.optInt("is_gpu_worker", 0) == 1 || obj.optBoolean("is_gpu_worker", false)
                nodesList.add(
                    ClusterNode(
                        nodeId = obj.optString("node_id", "desconocido"),
                        name = obj.optString("name", "Cliente"),
                        mode = obj.optString("mode", "desktop"),
                        hardwareFingerprint = obj.optString("hardware_fingerprint", ""),
                        ipAddress = obj.optString("ip_address", ""),
                        port = obj.optInt("port", 8765),
                        status = obj.optString("status", "offline"),
                        isGpuWorker = isGpu,
                        gpuInfo = obj.optString("gpu_info", ""),
                        hostname = meta?.optString("hostname", "") ?: "",
                        os = meta?.optString("os", "") ?: "",
                        arch = meta?.optString("arch", "") ?: "",
                        macPrimary = meta?.optString("mac_primary", "") ?: ""
                    )
                )
            }
        }

        val contArr = json.optJSONArray("containers")
        if (contArr != null) {
            for (i in 0 until contArr.length()) {
                val obj = contArr.optJSONObject(i) ?: continue
                containersList.add(
                    ClusterContainer(
                        name = obj.optString("name", ""),
                        status = obj.optString("status", ""),
                        image = obj.optString("image", ""),
                        engine = obj.optString("engine", "docker"),
                        nodeName = obj.optString("node_name", ""),
                        nodeIp = obj.optString("node_ip", "")
                    )
                )
            }
        }

        val gpuWorkerAvailable = json.optBoolean("gpu_worker_available", false)
        return Triple(nodesList, containersList, gpuWorkerAvailable)
    }

    @OptIn(ExperimentalMaterial3Api::class)
    @Composable
    fun JotaLinkScreen() {
        val scope = rememberCoroutineScope()
        var selectedTab by remember { mutableIntStateOf(0) }

        var isRecording by remember { mutableStateOf(false) }
        var replyText by remember { mutableStateOf("") }
        var lastPromptText by remember { mutableStateOf("") }
        var textChatInput by remember { mutableStateOf("") }

        var cpuLoad by remember { mutableDoubleStateOf(0.0) }
        var memPct by remember { mutableDoubleStateOf(0.0) }
        var diskPct by remember { mutableDoubleStateOf(0.0) }
        var activeWindowText by remember { mutableStateOf("Sin consultar") }
        var isOnline by remember { mutableStateOf(false) }

        var showHelpDialog by remember { mutableStateOf(false) }
        var inputUrl by remember { mutableStateOf(serverUrl) }
        var inputFallbackUrl by remember { mutableStateOf(serverFallbackUrl) }
        var inputKey by remember { mutableStateOf(apiKey) }
        var inputId by remember { mutableStateOf(deviceId) }
        var isScanningMdns by remember { mutableStateOf(false) }
        var wakeWordEnabled by remember { mutableStateOf(prefs.getBoolean("enable_wake_word", false)) }
        var savedMac by remember { mutableStateOf(prefs.getString("pc_mac", "34:5a:60:99:8a:f2") ?: "34:5a:60:99:8a:f2") }
        var showQrPairingDialog by remember { mutableStateOf(false) }
        var qrJsonInput by remember { mutableStateOf("") }

        // Cluster and health states
        var clusterRawJson by remember { mutableStateOf<JSONObject?>(null) }
        var hubHealthJson by remember { mutableStateOf<JSONObject?>(null) }
        var isClusterLoading by remember { mutableStateOf(false) }
        var clusterLatencyMs by remember { mutableLongStateOf(-1L) }
        var connectionTestResult by remember { mutableStateOf<Triple<Boolean, Long, String>?>(null) }
        var isTestingConnection by remember { mutableStateOf(false) }

        val chatMessages = remember { mutableStateListOf<ChatMessageItem>() }
        var pcBatteryPct by remember { mutableIntStateOf(-1) }
        var pcBatteryCharging by remember { mutableStateOf(false) }
        var mediaTitle by remember { mutableStateOf("") }
        var mediaArtist by remember { mutableStateOf("") }
        var mediaStatus by remember { mutableStateOf("") }
        var lastAudioBytes by remember { mutableStateOf<ByteArray?>(null) }

        val infiniteTransition = rememberInfiniteTransition(label = "voicePulse")
        val pulseScale by infiniteTransition.animateFloat(
            initialValue = 1f,
            targetValue = if (isRecording) 1.25f else 1f,
            animationSpec = infiniteRepeatable(
                animation = tween(700, easing = FastOutSlowInEasing),
                repeatMode = RepeatMode.Reverse
            ),
            label = "pulseScale"
        )
        val pulseAlpha by infiniteTransition.animateFloat(
            initialValue = 0.5f,
            targetValue = if (isRecording) 0f else 0.5f,
            animationSpec = infiniteRepeatable(
                animation = tween(700, easing = FastOutSlowInEasing),
                repeatMode = RepeatMode.Reverse
            ),
            label = "pulseAlpha"
        )

        var screenshotsList by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
        var currentScreenshotIndex by remember { mutableStateOf(0) }
        var currentScreenshotBitmap by remember { mutableStateOf<ImageBitmap?>(null) }
        var isScreenshotLoading by remember { mutableStateOf(false) }
        var showScreenshotDialog by remember { mutableStateOf(false) }

        fun loadScreenshotAtIndex(index: Int) {
            if (index < 0 || index >= screenshotsList.size) return
            currentScreenshotIndex = index
            val item = screenshotsList[index]
            val filename = item.optString("filename", "")
            val relPath = item.optString("relative_path", filename)
            val queryName = if (relPath.isNotEmpty()) relPath else filename
            isScreenshotLoading = true
            scope.launch {
                try {
                    val bytes = bridgeClient?.getScreenshotBytes(queryName)
                    if (bytes != null && bytes.isNotEmpty()) {
                        val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                        if (bmp != null) {
                            currentScreenshotBitmap = bmp.asImageBitmap()
                        }
                    }
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Error al cargar captura: ${e.message}", Toast.LENGTH_SHORT).show()
                } finally {
                    isScreenshotLoading = false
                }
            }
        }

        fun openScreenshotsGallery() {
            showScreenshotDialog = true
            isScreenshotLoading = true
            scope.launch {
                try {
                    val list = bridgeClient?.getPcScreenshots() ?: emptyList()
                    if (list.isNotEmpty()) {
                        screenshotsList = list
                        loadScreenshotAtIndex(0)
                    } else {
                        val captured = bridgeClient?.captureNewScreenshot() ?: emptyList()
                        if (captured.isNotEmpty()) {
                            screenshotsList = captured
                            loadScreenshotAtIndex(0)
                        } else {
                            val bytes = bridgeClient?.getPcScreenshot()
                            if (bytes != null && bytes.isNotEmpty()) {
                                val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                                if (bmp != null) {
                                    currentScreenshotBitmap = bmp.asImageBitmap()
                                }
                            }
                        }
                    }
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Error al listar capturas: ${e.message}", Toast.LENGTH_SHORT).show()
                } finally {
                    isScreenshotLoading = false
                }
            }
        }

        fun captureNewScreenshotNow() {
            isScreenshotLoading = true
            scope.launch {
                try {
                    val captured = bridgeClient?.captureNewScreenshot() ?: emptyList()
                    if (captured.isNotEmpty()) {
                        screenshotsList = captured
                        loadScreenshotAtIndex(0)
                        Toast.makeText(this@MainActivity, "Nueva captura tomada", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this@MainActivity, "No se pudo realizar la captura", Toast.LENGTH_SHORT).show()
                    }
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Fallo al capturar: ${e.message}", Toast.LENGTH_SHORT).show()
                } finally {
                    isScreenshotLoading = false
                }
            }
        }

        fun saveCurrentScreenshotToPhone() {
            scope.launch(Dispatchers.IO) {
                try {
                    val downloadsDir = android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS)
                    val filename = if (screenshotsList.isNotEmpty() && currentScreenshotIndex in screenshotsList.indices) {
                        screenshotsList[currentScreenshotIndex].optString("filename", "captura_pc.png")
                    } else {
                        "captura_pc_${System.currentTimeMillis()}.png"
                    }
                    val destFile = File(downloadsDir, filename)
                    val query = if (screenshotsList.isNotEmpty() && currentScreenshotIndex in screenshotsList.indices) {
                        val item = screenshotsList[currentScreenshotIndex]
                        item.optString("relative_path", item.optString("filename"))
                    } else filename
                    val ok = bridgeClient?.downloadPcFile(query, destFile) ?: false
                    withContext(Dispatchers.Main) {
                        if (ok) {
                            Toast.makeText(this@MainActivity, "Guardado en Descargas/$filename", Toast.LENGTH_SHORT).show()
                        } else {
                            Toast.makeText(this@MainActivity, "No se pudo guardar la captura", Toast.LENGTH_SHORT).show()
                        }
                    }
                } catch (e: Exception) {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(this@MainActivity, "Error al guardar: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }

        fun refreshClusterStatus() {
            isClusterLoading = true
            scope.launch {
                val start = System.currentTimeMillis()
                try {
                    val health = bridgeClient?.getHealth()
                    val cluster = bridgeClient?.getClusterStatus()
                    val pc = bridgeClient?.getPcStatus()
                    clusterLatencyMs = System.currentTimeMillis() - start
                    hubHealthJson = health
                    clusterRawJson = cluster

                    if (pc != null) {
                        cpuLoad = pc.optJSONObject("cpu")?.optDouble("load_1m", 0.0) ?: 0.0
                        memPct = pc.optJSONObject("memory")?.optDouble("percent_used", 0.0) ?: 0.0
                        diskPct = pc.optJSONObject("disk")?.optDouble("percent_used", 0.0) ?: 0.0
                        val win = pc.optJSONObject("active_window")?.optString("class", "Ninguna") ?: "Ninguna"
                        val title = pc.optJSONObject("active_window")?.optString("title", "") ?: ""
                        activeWindowText = if (title.isNotBlank()) "$win ($title)" else win

                        val bat = pc.optJSONObject("battery")
                        pcBatteryPct = if (bat?.optBoolean("present") == true) bat.optInt("percent", -1) else -1
                        pcBatteryCharging = bat?.optBoolean("charging") ?: false

                        val med = pc.optJSONObject("media")
                        mediaTitle = med?.optString("title", "") ?: ""
                        mediaArtist = med?.optString("artist", "") ?: ""
                        mediaStatus = med?.optString("status", "") ?: ""
                    }
                    isOnline = health != null || cluster != null || pc != null
                } catch (e: Exception) {
                    isOnline = false
                } finally {
                    isClusterLoading = false
                }
            }
        }

        LaunchedEffect(Unit) {
            refreshClusterStatus()
        }

        fun playAudioResponse(resp: JSONObject?): ByteArray? {
            if (resp == null) return null
            var bytes: ByteArray? = null
            val audioB64 = resp.optString("audio_base64", "")
            if (audioB64.isNotEmpty()) {
                try {
                    bytes = Base64.decode(audioB64, Base64.DEFAULT)
                    lastAudioBytes = bytes
                    scope.launch { audioHelper.playAudio(bytes) }
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            } else {
                val audioId = resp.optString("audio_id", "")
                if (audioId.isNotEmpty()) {
                    scope.launch {
                        try {
                            val dlBytes = bridgeClient?.downloadAudio(audioId)
                            if (dlBytes != null && dlBytes.isNotEmpty()) {
                                lastAudioBytes = dlBytes
                                audioHelper.playAudio(dlBytes)
                            }
                        } catch (e: Exception) {
                            e.printStackTrace()
                        }
                    }
                }
            }
            return bytes
        }

        Scaffold(
            containerColor = MaterialTheme.colorScheme.background,
            topBar = {
                Surface(
                    color = MaterialTheme.colorScheme.surface,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .statusBarsPadding()
                            .padding(horizontal = 20.dp, vertical = 12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Image(
                                painter = painterResource(id = R.drawable.ic_jota_logo),
                                contentDescription = "Jota Logo",
                                modifier = Modifier
                                    .size(26.dp)
                                    .clip(CircleShape)
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Column {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(
                                        "JOTA",
                                        fontWeight = FontWeight.ExtraBold,
                                        fontSize = 19.sp,
                                        letterSpacing = 1.sp,
                                        color = MaterialTheme.colorScheme.primary
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Surface(
                                        shape = CircleShape,
                                        color = if (isOnline) Color(0xFF1B382A) else Color(0xFF3B1F24)
                                    ) {
                                        Row(
                                            modifier = Modifier.padding(horizontal = 7.dp, vertical = 2.dp),
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Box(
                                                modifier = Modifier
                                                    .size(6.dp)
                                                    .clip(CircleShape)
                                                    .background(if (isOnline) Color(0xFF4CAF50) else Color(0xFFE57373))
                                            )
                                            Spacer(modifier = Modifier.width(5.dp))
                                            Text(
                                                text = if (isOnline) "ONLINE" else "OFFLINE",
                                                fontSize = 9.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = if (isOnline) Color(0xFF81C784) else Color(0xFFE57373)
                                            )
                                        }
                                    }
                                }
                                if (pcBatteryPct >= 0) {
                                    Text(
                                        text = "Bateria: $pcBatteryPct%${if (pcBatteryCharging) " (Cargando)" else ""}",
                                        fontSize = 10.sp,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }

                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            FilledTonalButton(
                                onClick = { showHelpDialog = true },
                                shape = CircleShape,
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)
                            ) {
                                Text("Comandos", fontSize = 11.sp)
                            }
                            FilledTonalButton(
                                onClick = { openScreenshotsGallery() },
                                shape = CircleShape,
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)
                            ) {
                                Text("Capturas", fontSize = 11.sp)
                            }
                        }
                    }
                }
            },
            bottomBar = {
                NavigationBar(
                    containerColor = MaterialTheme.colorScheme.surface,
                    tonalElevation = 8.dp
                ) {
                    NavigationBarItem(
                        selected = selectedTab == 0,
                        onClick = { selectedTab = 0 },
                        icon = { Icon(Icons.Default.Home, contentDescription = "Asistente") },
                        label = { Text("Asistente", fontSize = 11.sp) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = MaterialTheme.colorScheme.onPrimaryContainer,
                            selectedTextColor = MaterialTheme.colorScheme.primary,
                            indicatorColor = MaterialTheme.colorScheme.primaryContainer,
                            unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    )
                    NavigationBarItem(
                        selected = selectedTab == 1,
                        onClick = {
                            selectedTab = 1
                            refreshClusterStatus()
                        },
                        icon = { Icon(Icons.Default.Info, contentDescription = "Estado del Cluster") },
                        label = { Text("Estado", fontSize = 11.sp) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = MaterialTheme.colorScheme.onPrimaryContainer,
                            selectedTextColor = MaterialTheme.colorScheme.primary,
                            indicatorColor = MaterialTheme.colorScheme.primaryContainer,
                            unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    )
                    NavigationBarItem(
                        selected = selectedTab == 2,
                        onClick = { selectedTab = 2 },
                        icon = { Icon(Icons.Default.Settings, contentDescription = "Ajustes y Servidor") },
                        label = { Text("Ajustes", fontSize = 11.sp) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = MaterialTheme.colorScheme.onPrimaryContainer,
                            selectedTextColor = MaterialTheme.colorScheme.primary,
                            indicatorColor = MaterialTheme.colorScheme.primaryContainer,
                            unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    )
                }
            }
        ) { padding ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
            ) {
                when (selectedTab) {
                    0 -> AssistantTabContent(
                        isRecording = isRecording,
                        pulseScale = pulseScale,
                        pulseAlpha = pulseAlpha,
                        replyText = replyText,
                        lastPromptText = lastPromptText,
                        textChatInput = textChatInput,
                        chatMessages = chatMessages,
                        mediaTitle = mediaTitle,
                        mediaArtist = mediaArtist,
                        mediaStatus = mediaStatus,
                        onRecordStart = {
                            isRecording = true
                            audioHelper.startRecording()
                        },
                        onRecordStop = {
                            isRecording = false
                            val wavBytes = audioHelper.stopRecording()
                            scope.launch {
                                try {
                                    replyText = "Procesando en el PC..."
                                    val resp = bridgeClient?.askVoice(wavBytes)
                                    val p = resp?.optString("prompt", "") ?: ""
                                    val r = resp?.optString("response_text", "Sin respuesta") ?: ""
                                    lastPromptText = p
                                    replyText = r
                                    isOnline = true
                                    refreshClusterStatus()
                                    val audioDl = playAudioResponse(resp)

                                    val timeFormat = SimpleDateFormat("HH:mm", Locale.getDefault())
                                    val nowStr = timeFormat.format(Date())
                                    if (p.isNotBlank()) {
                                        chatMessages.add(ChatMessageItem(sender = "Tu", text = p, time = nowStr))
                                    }
                                    if (r.isNotBlank()) {
                                        chatMessages.add(ChatMessageItem(sender = "Jota", text = r, time = nowStr, audioBytes = audioDl))
                                    }

                                    val toolExecuted = resp?.optJSONObject("tool_executed")
                                    val toolName = toolExecuted?.optString("name", "") ?: ""
                                    if (toolName in listOf("screenshot", "show_screen", "screen_monitor", "screen", "captura")) {
                                        openScreenshotsGallery()
                                    }
                                } catch (e: Exception) {
                                    replyText = "Fallo de conexion: ${e.message}"
                                    isOnline = false
                                }
                            }
                        },
                        onTextInputChange = { textChatInput = it },
                        onSendText = {
                            if (textChatInput.isNotBlank()) {
                                val prompt = textChatInput
                                textChatInput = ""
                                scope.launch {
                                    try {
                                        lastPromptText = prompt
                                        replyText = "Consultando a Jota..."
                                        val timeFormat = SimpleDateFormat("HH:mm", Locale.getDefault())
                                        val nowStr = timeFormat.format(Date())
                                        chatMessages.add(ChatMessageItem(sender = "Tu", text = prompt, time = nowStr))

                                        val resp = bridgeClient?.askText(prompt, generateAudio = true, playOnPc = true)
                                        val r = resp?.optString("response_text", "") ?: ""
                                        replyText = r
                                        isOnline = true
                                        refreshClusterStatus()
                                        val audioDl = playAudioResponse(resp)
                                        if (r.isNotBlank()) {
                                            chatMessages.add(ChatMessageItem(sender = "Jota", text = r, time = nowStr, audioBytes = audioDl))
                                        }

                                        val toolExecuted = resp?.optJSONObject("tool_executed")
                                        val toolName = toolExecuted?.optString("name", "") ?: ""
                                        if (toolName in listOf("screenshot", "show_screen", "screen_monitor", "screen", "captura")) {
                                            openScreenshotsGallery()
                                        }
                                    } catch (e: Exception) {
                                        replyText = "Error: ${e.message}"
                                    }
                                }
                            }
                        },
                        onClearChat = { chatMessages.clear() },
                        onPlayAudio = { bytes -> scope.launch { audioHelper.playAudio(bytes) } },
                        onMediaAction = { action ->
                            scope.launch {
                                bridgeClient?.executePcAction(action)
                                refreshClusterStatus()
                            }
                        },
                        onPcLock = {
                            scope.launch {
                                val (_, msg) = bridgeClient?.executePcAction("lock") ?: Pair(false, "Sin conexion")
                                Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                            }
                        },
                        onPcMute = {
                            scope.launch {
                                val (_, msg) = bridgeClient?.executePcAction("mute") ?: Pair(false, "Sin conexion")
                                Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                            }
                        },
                        onCaptureScreen = { captureNewScreenshotNow() },
                        onPasteFromPc = {
                            scope.launch {
                                try {
                                    val pcClip = bridgeClient?.getPcClipboard() ?: ""
                                    if (pcClip.isNotBlank()) {
                                        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                        cm.setPrimaryClip(ClipData.newPlainText("PC Clipboard", pcClip))
                                        Toast.makeText(this@MainActivity, "Pegado en movil: ${pcClip.take(30)}...", Toast.LENGTH_SHORT).show()
                                    } else {
                                        Toast.makeText(this@MainActivity, "Portapapeles del PC vacio", Toast.LENGTH_SHORT).show()
                                    }
                                } catch (e: Exception) {
                                    Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                                }
                            }
                        },
                        onCopyToPc = {
                            val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                            val phoneClip = cm.primaryClip?.getItemAt(0)?.text?.toString() ?: ""
                            if (phoneClip.isNotBlank()) {
                                scope.launch {
                                    val ok = bridgeClient?.setPcClipboard(phoneClip) ?: false
                                    Toast.makeText(
                                        this@MainActivity,
                                        if (ok) "Copiado al PC con exito" else "Fallo al enviar al PC",
                                        Toast.LENGTH_SHORT
                                    ).show()
                                }
                            } else {
                                Toast.makeText(this@MainActivity, "Portapapeles del movil vacio", Toast.LENGTH_SHORT).show()
                            }
                        }
                    )
                    1 -> ClusterStatusTabContent(
                        isOnline = isOnline,
                        hubHealthJson = hubHealthJson,
                        clusterRawJson = clusterRawJson,
                        isLoading = isClusterLoading,
                        latencyMs = clusterLatencyMs,
                        currentUrl = serverUrl,
                        cpuLoad = cpuLoad,
                        memPct = memPct,
                        diskPct = diskPct,
                        activeWindowText = activeWindowText,
                        parsedCluster = parseClusterData(clusterRawJson),
                        onRefresh = { refreshClusterStatus() }
                    )
                    2 -> ServerConfigTabContent(
                        currentUrl = inputUrl,
                        currentFallbackUrl = inputFallbackUrl,
                        currentKey = inputKey,
                        currentDeviceId = inputId,
                        currentMac = savedMac,
                        isScanningMdns = isScanningMdns,
                        wakeWordEnabled = wakeWordEnabled,
                        isTestingConnection = isTestingConnection,
                        connectionTestResult = connectionTestResult,
                        onUrlChange = { inputUrl = it },
                        onFallbackUrlChange = { inputFallbackUrl = it },
                        onKeyChange = { inputKey = it },
                        onDeviceIdChange = { inputId = it },
                        onMacChange = { savedMac = it },
                        onSaveConfig = {
                            updateConnectionConfig(inputUrl, inputKey, inputId, inputFallbackUrl, savedMac)
                            refreshClusterStatus()
                        },
                        onApplyPreset = { url, fallback ->
                            inputUrl = url
                            inputFallbackUrl = fallback
                        },
                        onTestConnection = {
                            isTestingConnection = true
                            scope.launch {
                                val res = bridgeClient?.testServerConnection()
                                connectionTestResult = res
                                isTestingConnection = false
                                if (res?.first == true) {
                                    refreshClusterStatus()
                                }
                            }
                        },
                        onScanMdns = {
                            if (!isScanningMdns) {
                                isScanningMdns = true
                                Toast.makeText(this@MainActivity, "Buscando Jota en la red...", Toast.LENGTH_SHORT).show()
                                val dm = JotaDiscoveryManager(
                                    this@MainActivity,
                                    onServerFound = { host, port, name ->
                                        inputUrl = "http://$host:$port"
                                        isScanningMdns = false
                                        Toast.makeText(this@MainActivity, "Detectado: $name ($host:$port)", Toast.LENGTH_SHORT).show()
                                    },
                                    onDiscoveryFinished = { count ->
                                        isScanningMdns = false
                                        if (count == 0) {
                                            Toast.makeText(this@MainActivity, "No se detecto ningun PC por mDNS", Toast.LENGTH_SHORT).show()
                                        }
                                    }
                                )
                                dm.startDiscovery(5000L)
                            }
                        },
                        onWakeWordToggle = { checked ->
                            wakeWordEnabled = checked
                            prefs.edit().putBoolean("enable_wake_word", checked).apply()
                            val intent = Intent(this@MainActivity, JotaBridgeService::class.java).apply {
                                action = JotaBridgeService.ACTION_TOGGLE_WAKE_WORD
                                putExtra("enable", checked)
                            }
                            startService(intent)
                            Toast.makeText(
                                this@MainActivity,
                                if (checked) "Wake Word 'Jota' activo" else "Wake Word desactivado",
                                Toast.LENGTH_SHORT
                            ).show()
                        },
                        onSendWol = {
                            lifecycleScope.launch(Dispatchers.IO) {
                                val targetMac = savedMac.ifBlank { "34:5a:60:99:8a:f2" }
                                val ok = WakeOnLan.sendMagicPacket(targetMac)
                                withContext(Dispatchers.Main) {
                                    Toast.makeText(
                                        this@MainActivity,
                                        if (ok) "Paquete magico WoL enviado" else "Error enviando paquete WoL",
                                        Toast.LENGTH_SHORT
                                    ).show()
                                }
                            }
                        },
                        onOpenQrDialog = { showQrPairingDialog = true }
                    )
                }
            }

            if (showScreenshotDialog) {
                ScreenshotGalleryDialog(
                    screenshotsList = screenshotsList,
                    currentIndex = currentScreenshotIndex,
                    bitmap = currentScreenshotBitmap,
                    isLoading = isScreenshotLoading,
                    onDismiss = { showScreenshotDialog = false },
                    onCaptureNew = { captureNewScreenshotNow() },
                    onIndexChange = { loadScreenshotAtIndex(it) },
                    onSave = { saveCurrentScreenshotToPhone() }
                )
            }

            if (showHelpDialog) {
                HelpCommandsDialog(onDismiss = { showHelpDialog = false })
            }

            if (showQrPairingDialog) {
                QrPairingDialog(
                    qrJsonInput = qrJsonInput,
                    onInputChange = { qrJsonInput = it },
                    onDismiss = { showQrPairingDialog = false },
                    onPair = { jsonStr ->
                        try {
                            val json = JSONObject(jsonStr.trim())
                            val url = json.optString("url", inputUrl)
                            val fallback = json.optString("fallback_url", inputFallbackUrl)
                            val key = json.optString("api_key", inputKey)
                            val mac = json.optString("mac", "")
                            inputUrl = url
                            inputFallbackUrl = fallback
                            inputKey = key
                            if (mac.isNotEmpty()) {
                                savedMac = mac
                            }
                            updateConnectionConfig(url, key, inputId, fallback, mac)
                            showQrPairingDialog = false
                            refreshClusterStatus()
                            Toast.makeText(this@MainActivity, "Vinculacion aplicada", Toast.LENGTH_SHORT).show()
                        } catch (e: Exception) {
                            Toast.makeText(this@MainActivity, "Formato JSON no valido", Toast.LENGTH_SHORT).show()
                        }
                    }
                )
            }
        }
    }

    @Composable
    fun AssistantTabContent(
        isRecording: Boolean,
        pulseScale: Float,
        pulseAlpha: Float,
        replyText: String,
        lastPromptText: String,
        textChatInput: String,
        chatMessages: List<ChatMessageItem>,
        mediaTitle: String,
        mediaArtist: String,
        mediaStatus: String,
        onRecordStart: () -> Unit,
        onRecordStop: () -> Unit,
        onTextInputChange: (String) -> Unit,
        onSendText: () -> Unit,
        onClearChat: () -> Unit,
        onPlayAudio: (ByteArray) -> Unit,
        onMediaAction: (String) -> Unit,
        onPcLock: () -> Unit,
        onPcMute: () -> Unit,
        onCaptureScreen: () -> Unit,
        onPasteFromPc: () -> Unit,
        onCopyToPc: () -> Unit
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp, vertical = 12.dp)
                .verticalScroll(rememberScrollState()),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                shape = RoundedCornerShape(32.dp)
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = if (isRecording) "Escuchando... suelta para procesar" else "Manten pulsado para hablar",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = if (isRecording) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(modifier = Modifier.height(20.dp))

                    Box(
                        contentAlignment = Alignment.Center,
                        modifier = Modifier.size(170.dp)
                    ) {
                        if (isRecording) {
                            Box(
                                modifier = Modifier
                                    .size((136 * pulseScale).dp)
                                    .clip(CircleShape)
                                    .background(MaterialTheme.colorScheme.primary.copy(alpha = pulseAlpha))
                            )
                        }
                        Surface(
                            shape = CircleShape,
                            color = if (isRecording) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.primary,
                            shadowElevation = if (isRecording) 8.dp else 4.dp,
                            modifier = Modifier
                                .size(136.dp)
                                .pointerInput(Unit) {
                                    detectTapGestures(
                                        onPress = {
                                            onRecordStart()
                                            tryAwaitRelease()
                                            onRecordStop()
                                        }
                                    )
                                }
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Text(
                                    text = if (isRecording) "Soltar" else "Hablar",
                                    color = if (isRecording) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onPrimary,
                                    fontWeight = FontWeight.ExtraBold,
                                    fontSize = 18.sp,
                                    letterSpacing = 0.5.sp
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(20.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        OutlinedTextField(
                            value = textChatInput,
                            onValueChange = onTextInputChange,
                            placeholder = { Text("Escribe una peticion...") },
                            modifier = Modifier.weight(1f),
                            maxLines = 1,
                            shape = CircleShape
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Button(
                            onClick = onSendText,
                            shape = CircleShape,
                            contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp)
                        ) {
                            Text("Enviar", fontWeight = FontWeight.Bold)
                        }
                    }

                    if (lastPromptText.isNotEmpty() || replyText.isNotEmpty()) {
                        Spacer(modifier = Modifier.height(14.dp))
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(20.dp),
                            color = MaterialTheme.colorScheme.surface
                        ) {
                            Column(modifier = Modifier.padding(14.dp)) {
                                if (lastPromptText.isNotEmpty()) {
                                    Text("Tu: $lastPromptText", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                                if (replyText.isNotEmpty()) {
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Text("Jota: $replyText", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.primary)
                                }
                            }
                        }
                    }
                }
            }

            if (mediaTitle.isNotBlank()) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                    shape = RoundedCornerShape(28.dp)
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 20.dp, vertical = 16.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "REPRODUCIENDO",
                                fontSize = 10.sp,
                                letterSpacing = 1.sp,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.secondary
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = mediaTitle,
                                fontWeight = FontWeight.Bold,
                                fontSize = 14.sp,
                                maxLines = 1,
                                color = MaterialTheme.colorScheme.onSurface
                            )
                            if (mediaArtist.isNotBlank()) {
                                Text(
                                    text = mediaArtist,
                                    fontSize = 12.sp,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    maxLines = 1
                                )
                            }
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            FilledTonalIconButton(
                                onClick = { onMediaAction("previous") },
                                shape = CircleShape
                            ) {
                                Text("|<", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                            FilledTonalIconButton(
                                onClick = { onMediaAction("play_pause") },
                                shape = CircleShape,
                                colors = IconButtonDefaults.filledTonalIconButtonColors(
                                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                                    contentColor = MaterialTheme.colorScheme.onPrimaryContainer
                                )
                            ) {
                                Text(
                                    if (mediaStatus.lowercase().contains("play")) "||" else ">",
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                            FilledTonalIconButton(
                                onClick = { onMediaAction("next") },
                                shape = CircleShape
                            ) {
                                Text(">|", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                shape = RoundedCornerShape(28.dp)
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(
                        text = "ACCIONES RAPIDAS DEL ESCRITORIO",
                        fontWeight = FontWeight.Bold,
                        fontSize = 11.sp,
                        letterSpacing = 1.sp,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.height(14.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        FilledTonalButton(
                            onClick = onPcLock,
                            shape = RoundedCornerShape(18.dp),
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(vertical = 10.dp)
                        ) {
                            Text("Bloquear", fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                        }
                        FilledTonalButton(
                            onClick = onPcMute,
                            shape = RoundedCornerShape(18.dp),
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(vertical = 10.dp)
                        ) {
                            Text("Silenciar", fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                        }
                        FilledTonalButton(
                            onClick = onCaptureScreen,
                            shape = RoundedCornerShape(18.dp),
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(vertical = 10.dp)
                        ) {
                            Text("Captura", fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                        }
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        FilledTonalButton(
                            onClick = onPasteFromPc,
                            shape = RoundedCornerShape(18.dp),
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(vertical = 10.dp)
                        ) {
                            Text("Pegar del PC", fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                        }
                        FilledTonalButton(
                            onClick = onCopyToPc,
                            shape = RoundedCornerShape(18.dp),
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(vertical = 10.dp)
                        ) {
                            Text("Copiar al PC", fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                        }
                    }
                }
            }

            if (chatMessages.isNotEmpty()) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                    shape = RoundedCornerShape(28.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                "CONVERSACION",
                                fontWeight = FontWeight.Bold,
                                fontSize = 11.sp,
                                letterSpacing = 1.sp,
                                color = MaterialTheme.colorScheme.primary
                            )
                            TextButton(
                                onClick = onClearChat,
                                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)
                            ) {
                                Text("Limpiar", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }

                        chatMessages.takeLast(10).forEach { msg ->
                            val isUser = msg.sender == "Tu"
                            Column(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalAlignment = if (isUser) Alignment.End else Alignment.Start
                            ) {
                                Surface(
                                    shape = if (isUser) {
                                        RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp, bottomStart = 20.dp, bottomEnd = 4.dp)
                                    } else {
                                        RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp, bottomStart = 4.dp, bottomEnd = 20.dp)
                                    },
                                    color = if (isUser) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
                                    modifier = Modifier.widthIn(max = 300.dp)
                                ) {
                                    Row(
                                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column(modifier = Modifier.weight(1f, fill = false)) {
                                            Text(
                                                text = "${msg.sender} - ${msg.time}",
                                                fontSize = 10.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = if (isUser) MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f) else MaterialTheme.colorScheme.primary
                                            )
                                            Spacer(modifier = Modifier.height(3.dp))
                                            Text(
                                                text = msg.text,
                                                fontSize = 13.sp,
                                                color = if (isUser) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurface
                                            )
                                        }
                                        if (msg.audioBytes != null) {
                                            Spacer(modifier = Modifier.width(8.dp))
                                            FilledTonalButton(
                                                onClick = { onPlayAudio(msg.audioBytes) },
                                                shape = CircleShape,
                                                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)
                                            ) {
                                                Text("Audio", fontSize = 10.sp)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    @Composable
    fun ClusterStatusTabContent(
        isOnline: Boolean,
        hubHealthJson: JSONObject?,
        clusterRawJson: JSONObject?,
        isLoading: Boolean,
        latencyMs: Long,
        currentUrl: String,
        cpuLoad: Double,
        memPct: Double,
        diskPct: Double,
        activeWindowText: String,
        parsedCluster: Triple<List<ClusterNode>, List<ClusterContainer>, Boolean>,
        onRefresh: () -> Unit
    ) {
        val (nodesList, containersList, gpuWorkerAvailable) = parsedCluster
        val nodesTotal = clusterRawJson?.optInt("nodes_total", nodesList.size) ?: nodesList.size
        val nodesOnline = clusterRawJson?.optInt("nodes_online", nodesList.count { it.status == "online" }) ?: 0

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp, vertical = 12.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        "ESTADO DEL CLUSTER",
                        fontWeight = FontWeight.ExtraBold,
                        fontSize = 16.sp,
                        letterSpacing = 1.sp,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Text(
                        "Coordinador central y nodos satelite",
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                FilledTonalButton(
                    onClick = onRefresh,
                    enabled = !isLoading,
                    shape = CircleShape,
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                ) {
                    Icon(
                        Icons.Default.Refresh,
                        contentDescription = "Actualizar",
                        modifier = Modifier.size(14.dp)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(if (isLoading) "Actualizando..." else "Actualizar", fontSize = 11.sp)
                }
            }

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                shape = RoundedCornerShape(28.dp)
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(
                                "SERVIDOR HUB (24/7)",
                                fontWeight = FontWeight.Bold,
                                fontSize = 11.sp,
                                letterSpacing = 1.sp,
                                color = MaterialTheme.colorScheme.primary
                            )
                            Text(
                                "Nodo Maestro Coordinador",
                                fontSize = 13.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = MaterialTheme.colorScheme.onSurface
                            )
                        }
                        Surface(
                            shape = CircleShape,
                            color = if (isOnline) Color(0xFF1B382A) else Color(0xFF3B1F24)
                        ) {
                            Text(
                                text = if (isOnline) "HUB ONLINE" else "HUB OFFLINE",
                                fontSize = 10.sp,
                                fontWeight = FontWeight.Bold,
                                color = if (isOnline) Color(0xFF81C784) else Color(0xFFE57373),
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
                            )
                        }
                    }

                    Surface(
                        shape = RoundedCornerShape(16.dp),
                        color = MaterialTheme.colorScheme.surface,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(
                            modifier = Modifier.padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("Endpoint activo:", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(currentUrl, fontSize = 11.sp, fontWeight = FontWeight.Medium, color = MaterialTheme.colorScheme.primary)
                            }
                            if (latencyMs >= 0) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text("Latencia de respuesta:", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Text("${latencyMs} ms", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Color(0xFF81C784))
                                }
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("Nodos satelite en red:", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text("$nodesOnline de $nodesTotal online", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("Worker GPU dedicado:", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(
                                    if (gpuWorkerAvailable) "Disponible (Activo)" else "No disponible",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = if (gpuWorkerAvailable) Color(0xFF80CBC4) else MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Surface(
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(16.dp),
                            color = MaterialTheme.colorScheme.surface
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text("CARGA CPU", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Spacer(modifier = Modifier.height(2.dp))
                                Text("$cpuLoad", fontSize = 16.sp, fontWeight = FontWeight.ExtraBold)
                            }
                        }
                        Surface(
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(16.dp),
                            color = MaterialTheme.colorScheme.surface
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text("RAM USADA", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Spacer(modifier = Modifier.height(2.dp))
                                Text("${memPct.toInt()}%", fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, color = MaterialTheme.colorScheme.primary)
                            }
                        }
                        Surface(
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(16.dp),
                            color = MaterialTheme.colorScheme.surface
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text("DISCO", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Spacer(modifier = Modifier.height(2.dp))
                                Text("${diskPct.toInt()}%", fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, color = MaterialTheme.colorScheme.secondary)
                            }
                        }
                    }
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "CLIENTES Y SATELITES (${nodesList.size})",
                        fontWeight = FontWeight.Bold,
                        fontSize = 11.sp,
                        letterSpacing = 1.sp,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Text(
                        "Gestionados por Hub",
                        fontSize = 10.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                if (nodesList.isEmpty()) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                        shape = RoundedCornerShape(24.dp)
                    ) {
                        Column(
                            modifier = Modifier.padding(20.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Text(
                                "No hay clientes o satelites registrados en el Hub",
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                } else {
                    nodesList.forEachIndexed { index, node ->
                        val isNodeOnline = node.status == "online"
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                            shape = RoundedCornerShape(24.dp)
                        ) {
                            Column(
                                modifier = Modifier.padding(18.dp),
                                verticalArrangement = Arrangement.spacedBy(10.dp)
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = "Cliente ${index + 1}: ${node.name}",
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 14.sp,
                                            color = MaterialTheme.colorScheme.onSurface
                                        )
                                        Text(
                                            text = "ID: ${node.nodeId}",
                                            fontSize = 10.sp,
                                            fontFamily = FontFamily.Monospace,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                    Surface(
                                        shape = CircleShape,
                                        color = if (isNodeOnline) Color(0xFF1B382A) else Color(0xFF3B1F24)
                                    ) {
                                        Text(
                                            text = if (isNodeOnline) "ONLINE" else "OFFLINE",
                                            fontSize = 9.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = if (isNodeOnline) Color(0xFF81C784) else Color(0xFFE57373),
                                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                                        )
                                    }
                                }

                                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Surface(
                                        shape = CircleShape,
                                        color = MaterialTheme.colorScheme.primaryContainer
                                    ) {
                                        Text(
                                            text = "Modo: ${node.mode}",
                                            fontSize = 10.sp,
                                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
                                        )
                                    }
                                    if (node.isGpuWorker) {
                                        Surface(
                                            shape = CircleShape,
                                            color = Color(0xFF19363B)
                                        ) {
                                            Text(
                                                text = "GPU Worker Activo",
                                                fontSize = 10.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = Color(0xFF80CBC4),
                                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
                                            )
                                        }
                                    }
                                }

                                Surface(
                                    shape = RoundedCornerShape(14.dp),
                                    color = MaterialTheme.colorScheme.surface,
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Column(
                                        modifier = Modifier.padding(12.dp),
                                        verticalArrangement = Arrangement.spacedBy(4.dp)
                                    ) {
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween
                                        ) {
                                            Text("Direccion IP:", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                            Text("${node.ipAddress}:${node.port}", fontSize = 10.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
                                        }
                                        if (node.gpuInfo.isNotBlank()) {
                                            Row(
                                                modifier = Modifier.fillMaxWidth(),
                                                horizontalArrangement = Arrangement.SpaceBetween
                                            ) {
                                                Text("Chip GPU:", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                                Text(node.gpuInfo, fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, color = Color(0xFF80CBC4))
                                            }
                                        }
                                        if (node.os.isNotBlank()) {
                                            Row(
                                                modifier = Modifier.fillMaxWidth(),
                                                horizontalArrangement = Arrangement.SpaceBetween
                                            ) {
                                                Text("Sistema:", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                                Text("${node.os} (${node.arch})", fontSize = 10.sp)
                                            }
                                        }
                                        if (node.macPrimary.isNotBlank()) {
                                            Row(
                                                modifier = Modifier.fillMaxWidth(),
                                                horizontalArrangement = Arrangement.SpaceBetween
                                            ) {
                                                Text("MAC Primaria:", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                                Text(node.macPrimary, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            if (containersList.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(
                        "CONTENEDORES EN EL CLUSTER (${containersList.size})",
                        fontWeight = FontWeight.Bold,
                        fontSize = 11.sp,
                        letterSpacing = 1.sp,
                        color = MaterialTheme.colorScheme.primary
                    )

                    containersList.forEach { c ->
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                            shape = RoundedCornerShape(20.dp)
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(14.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(c.name, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                                    Text(c.image, fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                                    Text("Nodo: ${c.nodeName} (${c.nodeIp})", fontSize = 10.sp, color = MaterialTheme.colorScheme.primary)
                                }
                                Surface(
                                    shape = CircleShape,
                                    color = MaterialTheme.colorScheme.surface
                                ) {
                                    Text(
                                        text = "${c.engine.uppercase()} - ${c.status}",
                                        fontSize = 9.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = Color(0xFF81C784),
                                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    @Composable
    fun ServerConfigTabContent(
        currentUrl: String,
        currentFallbackUrl: String,
        currentKey: String,
        currentDeviceId: String,
        currentMac: String,
        isScanningMdns: Boolean,
        wakeWordEnabled: Boolean,
        isTestingConnection: Boolean,
        connectionTestResult: Triple<Boolean, Long, String>?,
        onUrlChange: (String) -> Unit,
        onFallbackUrlChange: (String) -> Unit,
        onKeyChange: (String) -> Unit,
        onDeviceIdChange: (String) -> Unit,
        onMacChange: (String) -> Unit,
        onSaveConfig: () -> Unit,
        onApplyPreset: (String, String) -> Unit,
        onTestConnection: () -> Unit,
        onScanMdns: () -> Unit,
        onWakeWordToggle: (Boolean) -> Unit,
        onSendWol: () -> Unit,
        onOpenQrDialog: () -> Unit
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp, vertical = 12.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Column {
                Text(
                    "AJUSTES DEL SISTEMA",
                    fontWeight = FontWeight.ExtraBold,
                    fontSize = 16.sp,
                    letterSpacing = 1.sp,
                    color = MaterialTheme.colorScheme.primary
                )
                Text(
                    "Configuracion de red, tokens y servidor",
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                shape = RoundedCornerShape(28.dp)
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text(
                        "Canales Rapidos",
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        listOf(
                            "Hub Tailscale" to ("http://100.85.176.113:8765" to "http://192.168.1.135:8765"),
                            "Hub LAN" to ("http://192.168.1.135:8765" to "http://100.85.176.113:8765"),
                            "Workstation" to ("http://100.81.222.82:8765" to "http://192.168.1.100:8765")
                        ).forEach { (label, urls) ->
                            val isSelected = currentUrl == urls.first
                            FilledTonalButton(
                                onClick = { onApplyPreset(urls.first, urls.second) },
                                shape = CircleShape,
                                colors = ButtonDefaults.filledTonalButtonColors(
                                    containerColor = if (isSelected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
                                    contentColor = if (isSelected) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurface
                                ),
                                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp),
                                modifier = Modifier.weight(1f)
                            ) {
                                Text(label, fontSize = 10.sp, maxLines = 1)
                            }
                        }
                    }

                    OutlinedTextField(
                        value = currentUrl,
                        onValueChange = onUrlChange,
                        label = { Text("Server URL Principal (Tailscale / Remoto)") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(16.dp)
                    )
                    OutlinedTextField(
                        value = currentFallbackUrl,
                        onValueChange = onFallbackUrlChange,
                        label = { Text("Fallback Server URL (LAN / Alternativo)") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(16.dp)
                    )
                    OutlinedTextField(
                        value = currentKey,
                        onValueChange = onKeyChange,
                        label = { Text("API Key / Token de Cluster") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(16.dp)
                    )
                    OutlinedTextField(
                        value = currentDeviceId,
                        onValueChange = onDeviceIdChange,
                        label = { Text("Device ID") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(16.dp)
                    )
                    OutlinedTextField(
                        value = currentMac,
                        onValueChange = onMacChange,
                        label = { Text("MAC del PC para Wake-on-LAN") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(16.dp)
                    )

                    Button(
                        onClick = onSaveConfig,
                        shape = CircleShape,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Guardar y Aplicar Configuracion", fontWeight = FontWeight.Bold)
                    }
                }
            }

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                shape = RoundedCornerShape(28.dp)
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Text(
                        "Prueba de Conexion",
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Text(
                        "Verifica en tiempo real si el Servidor Hub o Cliente responde al protocolo de salud y cluster.",
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )

                    FilledTonalButton(
                        onClick = onTestConnection,
                        enabled = !isTestingConnection,
                        shape = CircleShape,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(if (isTestingConnection) "Comprobando..." else "Probar Conexion con Servidor")
                    }

                    if (connectionTestResult != null) {
                        val (success, lat, msg) = connectionTestResult
                        Surface(
                            shape = RoundedCornerShape(16.dp),
                            color = if (success) Color(0xFF1B382A) else Color(0xFF3B1F24),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(modifier = Modifier.padding(14.dp)) {
                                Text(
                                    text = if (success) "Conexion Exitosa (${lat}ms)" else "Fallo al Conectar (${lat}ms)",
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 12.sp,
                                    color = if (success) Color(0xFF81C784) else Color(0xFFE57373)
                                )
                                Spacer(modifier = Modifier.height(2.dp))
                                Text(
                                    text = msg,
                                    fontSize = 11.sp,
                                    color = if (success) Color(0xFFC8E6C9) else Color(0xFFFFCDD2)
                                )
                            }
                        }
                    }
                }
            }

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                shape = RoundedCornerShape(28.dp)
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text(
                        "Herramientas de Red y Enlace",
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.primary
                    )

                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = MaterialTheme.colorScheme.surface
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 14.dp, vertical = 10.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text("Auto-detectar mDNS", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                                Text("Buscar Jota en la red local", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            FilledTonalButton(
                                onClick = onScanMdns,
                                enabled = !isScanningMdns,
                                shape = CircleShape,
                                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                            ) {
                                Text(if (isScanningMdns) "Buscando..." else "Escanear LAN", fontSize = 11.sp)
                            }
                        }
                    }

                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = MaterialTheme.colorScheme.surface
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 14.dp, vertical = 10.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text("Control de Energia (WoL)", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                                Text("MAC: ${currentMac.ifBlank { "Sin asignar" }}", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            FilledTonalButton(
                                onClick = onSendWol,
                                shape = CircleShape,
                                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                            ) {
                                Text("Despertar PC", fontSize = 11.sp)
                            }
                        }
                    }

                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = MaterialTheme.colorScheme.surface
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 14.dp, vertical = 10.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text("Emparejamiento QR / JSON", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                                Text("Configuracion automatica rapida", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            FilledTonalButton(
                                onClick = onOpenQrDialog,
                                shape = CircleShape,
                                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                            ) {
                                Text("Vincular", fontSize = 11.sp)
                            }
                        }
                    }

                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = MaterialTheme.colorScheme.surface
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 14.dp, vertical = 10.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text("Wake Word 'Jota' on-device", fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
                                Text("Escucha en segundo plano y vibra", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            Switch(
                                checked = wakeWordEnabled,
                                onCheckedChange = onWakeWordToggle
                            )
                        }
                    }
                }
            }
        }
    }

    @Composable
    fun ScreenshotGalleryDialog(
        screenshotsList: List<JSONObject>,
        currentIndex: Int,
        bitmap: ImageBitmap?,
        isLoading: Boolean,
        onDismiss: () -> Unit,
        onCaptureNew: () -> Unit,
        onIndexChange: (Int) -> Unit,
        onSave: () -> Unit
    ) {
        AlertDialog(
            onDismissRequest = onDismiss,
            shape = RoundedCornerShape(32.dp),
            containerColor = Color(0xFF161C26),
            tonalElevation = 6.dp,
            title = {
                Column {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("Capturas del PC", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Color(0xFFE2E8F0))
                        FilledTonalButton(
                            onClick = onCaptureNew,
                            enabled = !isLoading,
                            shape = CircleShape,
                            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                        ) {
                            Text("Capturar ahora", fontSize = 11.sp)
                        }
                    }
                    if (screenshotsList.isNotEmpty()) {
                        val currentItem = screenshotsList.getOrNull(currentIndex)
                        val dateStr = currentItem?.optString("date_str", "") ?: ""
                        val fname = currentItem?.optString("filename", "") ?: ""
                        Spacer(modifier = Modifier.height(6.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Surface(
                                shape = CircleShape,
                                color = MaterialTheme.colorScheme.primary.copy(alpha = 0.15f)
                            ) {
                                Text(
                                    "${currentIndex + 1} de ${screenshotsList.size}",
                                    fontSize = 11.sp,
                                    color = MaterialTheme.colorScheme.primary,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
                                )
                            }
                            Text(
                                dateStr.ifBlank { fname },
                                fontSize = 11.sp,
                                color = Color(0xFFA6ADC8)
                            )
                        }
                    }
                }
            },
            text = {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 180.dp, max = 360.dp),
                    contentAlignment = Alignment.Center
                ) {
                    if (isLoading) {
                        CircularProgressIndicator()
                    } else if (bitmap != null) {
                        Image(
                            bitmap = bitmap,
                            contentDescription = "Captura de pantalla",
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(20.dp))
                        )
                    } else {
                        Text(
                            "No hay capturas disponibles",
                            color = Color(0xFFA6ADC8),
                            fontSize = 13.sp
                        )
                    }
                }
            },
            confirmButton = {
                Column(modifier = Modifier.fillMaxWidth()) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            FilledTonalButton(
                                onClick = {
                                    if (currentIndex < screenshotsList.size - 1) {
                                        onIndexChange(currentIndex + 1)
                                    }
                                },
                                enabled = !isLoading && currentIndex < screenshotsList.size - 1,
                                shape = CircleShape,
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)
                            ) {
                                Text("< Anterior", fontSize = 11.sp)
                            }
                            FilledTonalButton(
                                onClick = {
                                    if (currentIndex > 0) {
                                        onIndexChange(currentIndex - 1)
                                    }
                                },
                                enabled = !isLoading && currentIndex > 0,
                                shape = CircleShape,
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)
                            ) {
                                Text("Siguiente >", fontSize = 11.sp)
                            }
                        }

                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            FilledTonalButton(
                                onClick = onSave,
                                enabled = bitmap != null,
                                shape = CircleShape,
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)
                            ) {
                                Text("Guardar", fontSize = 11.sp)
                            }
                            TextButton(
                                onClick = onDismiss,
                                shape = CircleShape
                            ) {
                                Text("Cerrar", fontSize = 12.sp)
                            }
                        }
                    }
                }
            }
        )
    }

    @Composable
    fun HelpCommandsDialog(onDismiss: () -> Unit) {
        AlertDialog(
            onDismissRequest = onDismiss,
            shape = RoundedCornerShape(32.dp),
            containerColor = Color(0xFF161C26),
            tonalElevation = 6.dp,
            title = {
                Text(
                    "Comandos Disponibles",
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp,
                    color = Color(0xFFE2E8F0)
                )
            },
            text = {
                Column(
                    modifier = Modifier.verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Text(
                        "Ejecutables mediante voz o texto:",
                        fontSize = 12.sp,
                        color = Color(0xFFA6ADC8)
                    )

                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = Color(0xFF1B2332),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("Multimedia y Audio", fontWeight = FontWeight.Bold, color = Color(0xFFCBA6F7), fontSize = 13.sp)
                            Text("sube / baja el volumen\nsilencia el audio / quita silencio\npausa la musica / reproduce\nsiguiente cancion / cancion anterior", fontSize = 12.sp, color = Color(0xFFE2E8F0))
                        }
                    }

                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = Color(0xFF1B2332),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("Control del PC y Escritorios", fontWeight = FontWeight.Bold, color = Color(0xFF89B4FA), fontSize = 13.sp)
                            Text("bloquea el PC / suspende el equipo\ncierra la ventana activa\npasa al escritorio [1-9]\nmueve la ventana al escritorio [1-9]\nhaz una captura de pantalla\ncomo esta el PC?", fontSize = 12.sp, color = Color(0xFFE2E8F0))
                        }
                    }

                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = Color(0xFF1B2332),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("Telefono Vinculado", fontWeight = FontWeight.Bold, color = Color(0xFFF9E2AF), fontSize = 13.sp)
                            Text("encuentra mi movil / haz sonar mi telefono\ncuanta bateria le queda al movil?\nenciende / apaga la linterna del movil\npon el movil en silencio\nmanda al movil la ultima captura\nmanda al movil el archivo [nombre]\nenvia al movil este enlace https://...", fontSize = 12.sp, color = Color(0xFFE2E8F0))
                        }
                    }

                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = Color(0xFF1B2332),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("Utilidades y Asistente", fontWeight = FontWeight.Bold, color = Color(0xFFA6E3A1), fontSize = 13.sp)
                            Text("que tiempo hace en [ciudad]? / va a llover hoy?\nanota [tarea o nota]\nque notas tengo pendientes?\navisame en [X] minutos para [motivo]\nabre [aplicacion] / buscame en la web [consulta]", fontSize = 12.sp, color = Color(0xFFE2E8F0))
                        }
                    }
                }
            },
            confirmButton = {
                FilledTonalButton(
                    onClick = onDismiss,
                    shape = CircleShape,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Entendido", fontWeight = FontWeight.Bold)
                }
            }
        )
    }

    @Composable
    fun QrPairingDialog(
        qrJsonInput: String,
        onInputChange: (String) -> Unit,
        onDismiss: () -> Unit,
        onPair: (String) -> Unit
    ) {
        AlertDialog(
            onDismissRequest = onDismiss,
            shape = RoundedCornerShape(32.dp),
            containerColor = Color(0xFF161C26),
            tonalElevation = 6.dp,
            title = {
                Text(
                    "Vincular con Jota PC",
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp,
                    color = Color(0xFFE2E8F0)
                )
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(
                        "Pega el texto generado por 'python -m bridge.qr' en tu PC o escaneado:",
                        fontSize = 12.sp,
                        color = Color(0xFFA6ADC8)
                    )
                    OutlinedTextField(
                        value = qrJsonInput,
                        onValueChange = onInputChange,
                        placeholder = { Text("{\"url\": \"http://...\", \"api_key\": \"...\"}") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(16.dp),
                        minLines = 3,
                        maxLines = 6
                    )
                }
            },
            confirmButton = {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TextButton(
                        onClick = onDismiss,
                        shape = CircleShape
                    ) {
                        Text("Cancelar", fontSize = 12.sp)
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    FilledTonalButton(
                        onClick = { onPair(qrJsonInput) },
                        shape = CircleShape
                    ) {
                        Text("Vincular", fontWeight = FontWeight.Bold)
                    }
                }
            }
        )
    }
}
