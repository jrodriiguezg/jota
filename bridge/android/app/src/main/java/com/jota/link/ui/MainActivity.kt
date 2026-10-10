package com.jota.link.ui

import android.Manifest
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
import androidx.lifecycle.lifecycleScope
import org.json.JSONObject
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import android.content.ClipData
import android.content.ClipboardManager
import androidx.compose.animation.core.*
import androidx.core.content.ContextCompat
import androidx.compose.ui.res.painterResource
import com.jota.link.R
import com.jota.link.audio.AudioHelper
import com.jota.link.network.BridgeClient
import com.jota.link.network.JotaDiscoveryManager
import com.jota.link.network.WakeOnLan
import com.jota.link.service.JotaBridgeService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
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

class MainActivity : ComponentActivity() {
    private val audioHelper = AudioHelper()
    private var bridgeClient: BridgeClient? = null
    private lateinit var prefs: SharedPreferences

    private var serverUrl by mutableStateOf("http://100.81.222.82:8765")
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

        serverUrl = prefs.getString("server_url", "http://100.81.222.82:8765") ?: "http://100.81.222.82:8765"
        apiKey = prefs.getString("api_key", "jota-secret-tailscale-key") ?: "jota-secret-tailscale-key"
        deviceId = prefs.getString("device_id", "android_user") ?: "android_user"

        bridgeClient = BridgeClient(this, serverUrl, apiKey, deviceId)

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
            putExtra("apiKey", apiKey)
            putExtra("deviceId", deviceId)
            putExtra("enableWakeWord", wakeWordPref)
        }
        startForegroundService(intent)
    }

    private fun updateConnectionConfig(newUrl: String, newKey: String, newId: String, newMac: String? = null) {
        serverUrl = newUrl.trim()
        apiKey = newKey.trim()
        deviceId = newId.trim()

        prefs.edit().apply {
            putString("server_url", serverUrl)
            putString("api_key", apiKey)
            putString("device_id", deviceId)
            if (!newMac.isNullOrBlank()) {
                putString("pc_mac", newMac.trim())
            }
            apply()
        }

        bridgeClient?.disconnect()
        bridgeClient = BridgeClient(this, serverUrl, apiKey, deviceId)
        startBridgeService()

        // Autodescubrir MAC del PC para Wake-on-LAN
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
            val client = bridgeClient ?: BridgeClient(this@MainActivity, serverUrl, apiKey, deviceId)
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
            val client = bridgeClient ?: BridgeClient(this@MainActivity, serverUrl, apiKey, deviceId)
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

    @OptIn(ExperimentalMaterial3Api::class)
    @Composable
    fun JotaLinkScreen() {
        val scope = rememberCoroutineScope()
        var isRecording by remember { mutableStateOf(false) }
        var replyText by remember { mutableStateOf("") }
        var lastPromptText by remember { mutableStateOf("") }
        var textChatInput by remember { mutableStateOf("") }

        var cpuLoad by remember { mutableDoubleStateOf(0.0) }
        var memPct by remember { mutableDoubleStateOf(0.0) }
        var diskPct by remember { mutableDoubleStateOf(0.0) }
        var activeWindowText by remember { mutableStateOf("Sin consultar") }
        var isOnline by remember { mutableStateOf(false) }

        var showSettings by remember { mutableStateOf(false) }
        var showHelpDialog by remember { mutableStateOf(false) }
        var inputUrl by remember { mutableStateOf(serverUrl) }
        var inputKey by remember { mutableStateOf(apiKey) }
        var inputId by remember { mutableStateOf(deviceId) }
        var isScanningMdns by remember { mutableStateOf(false) }
        var wakeWordEnabled by remember { mutableStateOf(prefs.getBoolean("enable_wake_word", false)) }
        var savedMac by remember { mutableStateOf(prefs.getString("pc_mac", "") ?: "") }
        var showQrPairingDialog by remember { mutableStateOf(false) }
        var qrJsonInput by remember { mutableStateOf("") }

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

        fun refreshPcStatus() {
            scope.launch {
                try {
                    val status = bridgeClient?.getPcStatus()
                    if (status != null) {
                        cpuLoad = status.optJSONObject("cpu")?.optDouble("load_1m", 0.0) ?: 0.0
                        memPct = status.optJSONObject("memory")?.optDouble("percent_used", 0.0) ?: 0.0
                        diskPct = status.optJSONObject("disk")?.optDouble("percent_used", 0.0) ?: 0.0
                        val win = status.optJSONObject("active_window")?.optString("class", "Ninguna") ?: "Ninguna"
                        val title = status.optJSONObject("active_window")?.optString("title", "") ?: ""
                        activeWindowText = if (title.isNotBlank()) "$win ($title)" else win

                        val bat = status.optJSONObject("battery")
                        pcBatteryPct = if (bat?.optBoolean("present") == true) bat.optInt("percent", -1) else -1
                        pcBatteryCharging = bat?.optBoolean("charging") ?: false

                        val med = status.optJSONObject("media")
                        mediaTitle = med?.optString("title", "") ?: ""
                        mediaArtist = med?.optString("artist", "") ?: ""
                        mediaStatus = med?.optString("status", "") ?: ""

                        isOnline = true
                    }
                } catch (e: Exception) {
                    activeWindowText = "Fallo al conectar"
                    isOnline = false
                }
            }
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
                            .padding(horizontal = 20.dp, vertical = 14.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Image(
                                    painter = painterResource(id = R.mipmap.ic_launcher),
                                    contentDescription = "Jota Logo",
                                    modifier = Modifier
                                        .size(24.dp)
                                        .clip(CircleShape)
                                )
                                Spacer(modifier = Modifier.width(10.dp))
                                Text(
                                    "JOTA",
                                    fontWeight = FontWeight.ExtraBold,
                                    fontSize = 20.sp,
                                    letterSpacing = 1.sp,
                                    color = MaterialTheme.colorScheme.primary
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Surface(
                                    shape = CircleShape,
                                    color = if (isOnline) Color(0xFF1B382A) else Color(0xFF3B1F24)
                                ) {
                                    Row(
                                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Box(
                                            modifier = Modifier
                                                .size(7.dp)
                                                .clip(CircleShape)
                                                .background(if (isOnline) Color(0xFF4CAF50) else Color(0xFFE57373))
                                        )
                                        Spacer(modifier = Modifier.width(5.dp))
                                        Text(
                                            text = if (isOnline) "ONLINE" else "OFFLINE",
                                            fontSize = 10.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = if (isOnline) Color(0xFF81C784) else Color(0xFFE57373)
                                        )
                                    }
                                }
                            }
                            if (pcBatteryPct >= 0) {
                                Spacer(modifier = Modifier.height(2.dp))
                                Text(
                                    text = "Batería PC: $pcBatteryPct%${if (pcBatteryCharging) " (Cargando)" else ""}",
                                    fontSize = 11.sp,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }

                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            FilledTonalButton(
                                onClick = { showHelpDialog = true },
                                shape = CircleShape,
                                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                            ) {
                                Text("Comandos", fontSize = 11.sp)
                            }
                            Button(
                                onClick = { showSettings = !showSettings },
                                shape = CircleShape,
                                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                            ) {
                                Text(if (showSettings) "Cerrar" else "Ajustes", fontSize = 11.sp)
                            }
                        }
                    }
                }
            }
        ) { padding ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(horizontal = 16.dp, vertical = 12.dp)
                    .verticalScroll(rememberScrollState()),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // ── Panel Desplegable de Ajustes (Material 3 Expressive) ──
                AnimatedVisibility(visible = showSettings) {
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
                                "Conexión y Red",
                                fontWeight = FontWeight.Bold,
                                fontSize = 16.sp,
                                color = MaterialTheme.colorScheme.primary
                            )

                            // 1. Auto-descubrimiento ZeroConf / mDNS
                            Surface(
                                shape = RoundedCornerShape(20.dp),
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
                                        onClick = {
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
                                                            Toast.makeText(this@MainActivity, "No se detectó ningún PC por mDNS", Toast.LENGTH_SHORT).show()
                                                        }
                                                    }
                                                )
                                                dm.startDiscovery(5000L)
                                            }
                                        },
                                        enabled = !isScanningMdns,
                                        shape = CircleShape,
                                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                                    ) {
                                        Text(if (isScanningMdns) "Buscando..." else "Escanear LAN", fontSize = 11.sp)
                                    }
                                }
                            }

                            // 2. Presets de Canales Rápidos
                            Text("Canales Rápidos", fontSize = 11.sp, fontWeight = FontWeight.Medium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                listOf(
                                    "Cable ADB" to "http://127.0.0.1:8765",
                                    "USB Tether" to "http://192.168.42.1:8765",
                                    "Bluetooth" to "http://192.168.44.1:8765"
                                ).forEach { (label, url) ->
                                    val isSelected = inputUrl == url
                                    FilledTonalButton(
                                        onClick = { inputUrl = url },
                                        shape = CircleShape,
                                        colors = ButtonDefaults.filledTonalButtonColors(
                                            containerColor = if (isSelected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
                                            contentColor = if (isSelected) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurface
                                        ),
                                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                                        modifier = Modifier.weight(1f)
                                    ) {
                                        Text(label, fontSize = 10.sp, maxLines = 1)
                                    }
                                }
                            }

                            OutlinedTextField(
                                value = inputUrl,
                                onValueChange = { inputUrl = it },
                                label = { Text("Server URL") },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(16.dp)
                            )
                            OutlinedTextField(
                                value = inputKey,
                                onValueChange = { inputKey = it },
                                label = { Text("API Key") },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(16.dp)
                            )
                            OutlinedTextField(
                                value = inputId,
                                onValueChange = { inputId = it },
                                label = { Text("Device ID") },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(16.dp)
                            )

                            // 3. Wake Word on-device ("Jota")
                            Surface(
                                shape = RoundedCornerShape(20.dp),
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
                                        Text("Escucha en segundo plano y vibra al activar", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                    Switch(
                                        checked = wakeWordEnabled,
                                        onCheckedChange = { checked ->
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
                                        }
                                    )
                                }
                            }

                            // 4. Wake-on-LAN (WoL) y Emparejamiento QR
                            Surface(
                                shape = RoundedCornerShape(20.dp),
                                color = MaterialTheme.colorScheme.surface
                            ) {
                                Column(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(horizontal = 14.dp, vertical = 10.dp),
                                    verticalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text("Control de Energia (WoL)", fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
                                            Text(
                                                if (savedMac.isNotBlank()) "MAC: $savedMac" else "MAC no detectada todavia",
                                                fontSize = 10.sp,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                        }
                                        FilledTonalButton(
                                            onClick = {
                                                lifecycleScope.launch(Dispatchers.IO) {
                                                    val targetMac = savedMac.ifBlank { "34:5A:60:99:8A:F2" }
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
                                            shape = CircleShape,
                                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)
                                        ) {
                                            Text("Despertar PC", fontSize = 11.sp)
                                        }
                                    }

                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text("Vincular con QR / JSON", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                        FilledTonalButton(
                                            onClick = { showQrPairingDialog = true },
                                            shape = CircleShape,
                                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)
                                        ) {
                                            Text("Escanear / Pegar", fontSize = 11.sp)
                                        }
                                    }
                                }
                            }

                            Button(
                                onClick = {
                                    updateConnectionConfig(inputUrl, inputKey, inputId)
                                    showSettings = false
                                },
                                shape = CircleShape,
                                modifier = Modifier.align(Alignment.End)
                            ) {
                                Text("Guardar y Conectar")
                            }
                        }
                    }
                }

                // ── Seccion 1: Asistente y Boton Hero de Voz (Android 16 Expressive) ──
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
                            text = if (isRecording) "Escuchando... suelta para procesar" else "Mantén pulsado para hablar",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = if (isRecording) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.onSurface
                        )
                        Spacer(modifier = Modifier.height(20.dp))

                        // Boton Hero con halo pulsante Material 3
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
                                                isRecording = true
                                                audioHelper.startRecording()
                                                tryAwaitRelease()
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
                                                        refreshPcStatus()
                                                        val audioDl = playAudioResponse(resp)

                                                        val timeFormat = SimpleDateFormat("HH:mm", Locale.getDefault())
                                                        val nowStr = timeFormat.format(Date())
                                                        if (p.isNotBlank()) {
                                                            chatMessages.add(ChatMessageItem(sender = "Tú", text = p, time = nowStr))
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

                        // Entrada de texto estilo Pill SearchBar
                        Spacer(modifier = Modifier.height(20.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            OutlinedTextField(
                                value = textChatInput,
                                onValueChange = { textChatInput = it },
                                placeholder = { Text("Escribe una petición...") },
                                modifier = Modifier.weight(1f),
                                maxLines = 1,
                                shape = CircleShape
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Button(
                                onClick = {
                                    if (textChatInput.isNotBlank()) {
                                        val prompt = textChatInput
                                        textChatInput = ""
                                        scope.launch {
                                            try {
                                                lastPromptText = prompt
                                                replyText = "Consultando a Jota..."
                                                val timeFormat = SimpleDateFormat("HH:mm", Locale.getDefault())
                                                val nowStr = timeFormat.format(Date())
                                                chatMessages.add(ChatMessageItem(sender = "Tú", text = prompt, time = nowStr))

                                                val resp = bridgeClient?.askText(prompt, generateAudio = true, playOnPc = true)
                                                val r = resp?.optString("response_text", "") ?: ""
                                                replyText = r
                                                isOnline = true
                                                refreshPcStatus()
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
                                shape = CircleShape,
                                contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp)
                            ) {
                                Text("Enviar", fontWeight = FontWeight.Bold)
                            }
                        }

                        // Respuesta rápida
                        if (lastPromptText.isNotEmpty() || replyText.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(14.dp))
                            Surface(
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(20.dp),
                                color = MaterialTheme.colorScheme.surface
                            ) {
                                Column(modifier = Modifier.padding(14.dp)) {
                                    if (lastPromptText.isNotEmpty()) {
                                        Text("Tú: $lastPromptText", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
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

                // ── Seccion 2: Reproductor Multimedia (Estilo Android 16) ──
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
                                    onClick = {
                                        scope.launch {
                                            bridgeClient?.executePcAction("previous")
                                            refreshPcStatus()
                                        }
                                    },
                                    shape = CircleShape
                                ) {
                                    Text("|<", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                }
                                FilledTonalIconButton(
                                    onClick = {
                                        scope.launch {
                                            bridgeClient?.executePcAction("play_pause")
                                            refreshPcStatus()
                                        }
                                    },
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
                                    onClick = {
                                        scope.launch {
                                            bridgeClient?.executePcAction("next")
                                            refreshPcStatus()
                                        }
                                    },
                                    shape = CircleShape
                                ) {
                                    Text(">|", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                }
                            }
                        }
                    }
                }

                // ── Seccion 3: Acciones Rápidas del PC (Tiles Android 16) ──
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                    shape = RoundedCornerShape(28.dp)
                ) {
                    Column(modifier = Modifier.padding(20.dp)) {
                        Text(
                            text = "ACCIONES DEL PC",
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
                                onClick = {
                                    scope.launch {
                                        val (_, msg) = bridgeClient?.executePcAction("lock") ?: Pair(false, "Sin conexion")
                                        Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                                    }
                                },
                                shape = RoundedCornerShape(18.dp),
                                modifier = Modifier.weight(1f),
                                contentPadding = PaddingValues(vertical = 10.dp)
                            ) {
                                Text("Bloquear", fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                            }
                            FilledTonalButton(
                                onClick = {
                                    scope.launch {
                                        val (_, msg) = bridgeClient?.executePcAction("mute") ?: Pair(false, "Sin conexion")
                                        Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                                    }
                                },
                                shape = RoundedCornerShape(18.dp),
                                modifier = Modifier.weight(1f),
                                contentPadding = PaddingValues(vertical = 10.dp)
                            ) {
                                Text("Silenciar", fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                            }
                            FilledTonalButton(
                                onClick = { captureNewScreenshotNow() },
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
                                onClick = {
                                    scope.launch {
                                        try {
                                            val pcClip = bridgeClient?.getPcClipboard() ?: ""
                                            if (pcClip.isNotBlank()) {
                                                val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                                cm.setPrimaryClip(ClipData.newPlainText("PC Clipboard", pcClip))
                                                Toast.makeText(this@MainActivity, "Pegado en móvil: ${pcClip.take(30)}...", Toast.LENGTH_SHORT).show()
                                            } else {
                                                Toast.makeText(this@MainActivity, "Portapapeles del PC vacío", Toast.LENGTH_SHORT).show()
                                            }
                                        } catch (e: Exception) {
                                            Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                                        }
                                    }
                                },
                                shape = RoundedCornerShape(18.dp),
                                modifier = Modifier.weight(1f),
                                contentPadding = PaddingValues(vertical = 10.dp)
                            ) {
                                Text("Pegar del PC", fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                            }
                            FilledTonalButton(
                                onClick = {
                                    val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                    val phoneClip = cm.primaryClip?.getItemAt(0)?.text?.toString() ?: ""
                                    if (phoneClip.isNotBlank()) {
                                        scope.launch {
                                            val ok = bridgeClient?.setPcClipboard(phoneClip) ?: false
                                            Toast.makeText(
                                                this@MainActivity,
                                                if (ok) "Copiado al PC con éxito" else "Fallo al enviar al PC",
                                                Toast.LENGTH_SHORT
                                            ).show()
                                        }
                                    } else {
                                        Toast.makeText(this@MainActivity, "Portapapeles del móvil vacío", Toast.LENGTH_SHORT).show()
                                    }
                                },
                                shape = RoundedCornerShape(18.dp),
                                modifier = Modifier.weight(1f),
                                contentPadding = PaddingValues(vertical = 10.dp)
                            ) {
                                Text("Copiar al PC", fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                            }
                        }
                    }
                }

                // ── Seccion 4: Historial de Conversación (Burbujas Expressive) ──
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
                                    "CONVERSACIÓN",
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 11.sp,
                                    letterSpacing = 1.sp,
                                    color = MaterialTheme.colorScheme.primary
                                )
                                TextButton(
                                    onClick = { chatMessages.clear() },
                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)
                                ) {
                                    Text("Limpiar", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }

                            chatMessages.takeLast(10).forEach { msg ->
                                val isUser = msg.sender == "Tú"
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
                                                    onClick = {
                                                        scope.launch { audioHelper.playAudio(msg.audioBytes) }
                                                    },
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

                // ── Seccion 5: Estado y Métricas del PC (Tiles Android 16) ──
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                    shape = RoundedCornerShape(28.dp)
                ) {
                    Column(modifier = Modifier.padding(20.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    "ESTADO DEL PC",
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 11.sp,
                                    letterSpacing = 1.sp,
                                    color = MaterialTheme.colorScheme.primary
                                )
                                Spacer(modifier = Modifier.height(2.dp))
                                Text(
                                    text = activeWindowText,
                                    fontSize = 12.sp,
                                    maxLines = 1,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                FilledTonalButton(
                                    onClick = { openScreenshotsGallery() },
                                    shape = CircleShape,
                                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)
                                ) {
                                    Text("Capturas", fontSize = 11.sp)
                                }
                                Button(
                                    onClick = { refreshPcStatus() },
                                    shape = CircleShape,
                                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)
                                ) {
                                    Text("Actualizar", fontSize = 11.sp)
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(16.dp))

                        // Grid 2x2 de métricas estilo Android 16
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            // Tile CPU
                            Surface(
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(20.dp),
                                color = MaterialTheme.colorScheme.surface
                            ) {
                                Column(modifier = Modifier.padding(14.dp)) {
                                    Text("CPU", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Text("$cpuLoad", fontSize = 18.sp, fontWeight = FontWeight.ExtraBold, color = MaterialTheme.colorScheme.onSurface)
                                    Spacer(modifier = Modifier.height(6.dp))
                                    Text("Carga media (1m)", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }

                            // Tile RAM
                            Surface(
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(20.dp),
                                color = MaterialTheme.colorScheme.surface
                            ) {
                                Column(modifier = Modifier.padding(14.dp)) {
                                    Text("RAM", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Text("${memPct.toInt()}%", fontSize = 18.sp, fontWeight = FontWeight.ExtraBold, color = MaterialTheme.colorScheme.primary)
                                    Spacer(modifier = Modifier.height(6.dp))
                                    LinearProgressIndicator(
                                        progress = { (memPct / 100.0).toFloat().coerceIn(0f, 1f) },
                                        modifier = Modifier.fillMaxWidth().height(6.dp).clip(CircleShape)
                                    )
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(10.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            // Tile Disco
                            Surface(
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(20.dp),
                                color = MaterialTheme.colorScheme.surface
                            ) {
                                Column(modifier = Modifier.padding(14.dp)) {
                                    Text("DISCO", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Text("${diskPct.toInt()}%", fontSize = 18.sp, fontWeight = FontWeight.ExtraBold, color = MaterialTheme.colorScheme.secondary)
                                    Spacer(modifier = Modifier.height(6.dp))
                                    LinearProgressIndicator(
                                        progress = { (diskPct / 100.0).toFloat().coerceIn(0f, 1f) },
                                        modifier = Modifier.fillMaxWidth().height(6.dp).clip(CircleShape)
                                    )
                                }
                            }

                            // Tile Batería
                            Surface(
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(20.dp),
                                color = MaterialTheme.colorScheme.surface
                            ) {
                                Column(modifier = Modifier.padding(14.dp)) {
                                    Text("BATERÍA PC", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Spacer(modifier = Modifier.height(4.dp))
                                    if (pcBatteryPct >= 0) {
                                        Text(
                                            "$pcBatteryPct%",
                                            fontSize = 18.sp,
                                            fontWeight = FontWeight.ExtraBold,
                                            color = if (pcBatteryPct <= 20) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.tertiary
                                        )
                                        Spacer(modifier = Modifier.height(6.dp))
                                        LinearProgressIndicator(
                                            progress = { (pcBatteryPct / 100.0).toFloat().coerceIn(0f, 1f) },
                                            modifier = Modifier.fillMaxWidth().height(6.dp).clip(CircleShape),
                                            color = if (pcBatteryPct <= 20) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.tertiary
                                        )
                                    } else {
                                        Text("AC", fontSize = 18.sp, fontWeight = FontWeight.ExtraBold, color = MaterialTheme.colorScheme.tertiary)
                                        Spacer(modifier = Modifier.height(6.dp))
                                        Text("Corriente continua", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── Modal de Capturas de Pantalla del PC (Historial y Captura) ──
            if (showScreenshotDialog) {
                AlertDialog(
                    onDismissRequest = { showScreenshotDialog = false },
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
                                    onClick = { captureNewScreenshotNow() },
                                    enabled = !isScreenshotLoading,
                                    shape = CircleShape,
                                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                                ) {
                                    Text("Capturar ahora", fontSize = 11.sp)
                                }
                            }
                            if (screenshotsList.isNotEmpty()) {
                                val currentItem = screenshotsList.getOrNull(currentScreenshotIndex)
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
                                            "${currentScreenshotIndex + 1} de ${screenshotsList.size}",
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
                            if (isScreenshotLoading) {
                                CircularProgressIndicator()
                            } else if (currentScreenshotBitmap != null) {
                                Image(
                                    bitmap = currentScreenshotBitmap!!,
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
                                            if (currentScreenshotIndex < screenshotsList.size - 1) {
                                                loadScreenshotAtIndex(currentScreenshotIndex + 1)
                                            }
                                        },
                                        enabled = !isScreenshotLoading && currentScreenshotIndex < screenshotsList.size - 1,
                                        shape = CircleShape,
                                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)
                                    ) {
                                        Text("< Anterior", fontSize = 11.sp)
                                    }
                                    FilledTonalButton(
                                        onClick = {
                                            if (currentScreenshotIndex > 0) {
                                                loadScreenshotAtIndex(currentScreenshotIndex - 1)
                                            }
                                        },
                                        enabled = !isScreenshotLoading && currentScreenshotIndex > 0,
                                        shape = CircleShape,
                                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)
                                    ) {
                                        Text("Siguiente >", fontSize = 11.sp)
                                    }
                                }

                                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                    FilledTonalButton(
                                        onClick = { saveCurrentScreenshotToPhone() },
                                        enabled = currentScreenshotBitmap != null,
                                        shape = CircleShape,
                                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)
                                    ) {
                                        Text("Guardar", fontSize = 11.sp)
                                    }
                                    TextButton(
                                        onClick = { showScreenshotDialog = false },
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

            // ── Modal de Ayuda con Comandos Disponibles ──
            if (showHelpDialog) {
                AlertDialog(
                    onDismissRequest = { showHelpDialog = false },
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
                            onClick = { showHelpDialog = false },
                            shape = CircleShape,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text("Entendido", fontWeight = FontWeight.Bold)
                        }
                    }
                )
            }

            // ── Modal de Emparejamiento por QR / JSON ──
            if (showQrPairingDialog) {
                AlertDialog(
                    onDismissRequest = { showQrPairingDialog = false },
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
                                onValueChange = { qrJsonInput = it },
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
                                onClick = { showQrPairingDialog = false },
                                shape = CircleShape
                            ) {
                                Text("Cancelar", fontSize = 12.sp)
                            }
                            Spacer(modifier = Modifier.width(8.dp))
                            FilledTonalButton(
                                onClick = {
                                    try {
                                        val json = JSONObject(qrJsonInput.trim())
                                        val url = json.optString("url", inputUrl)
                                        val key = json.optString("api_key", inputKey)
                                        val mac = json.optString("mac", "")
                                        inputUrl = url
                                        inputKey = key
                                        if (mac.isNotEmpty()) {
                                            savedMac = mac
                                        }
                                        updateConnectionConfig(url, key, inputId, mac)
                                        showQrPairingDialog = false
                                        showSettings = false
                                        Toast.makeText(this@MainActivity, "Vinculacion aplicada", Toast.LENGTH_SHORT).show()
                                    } catch (e: Exception) {
                                        Toast.makeText(this@MainActivity, "Formato JSON no valido", Toast.LENGTH_SHORT).show()
                                    }
                                },
                                shape = CircleShape
                            ) {
                                Text("Vincular", fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                )
            }
        }
    }
}
