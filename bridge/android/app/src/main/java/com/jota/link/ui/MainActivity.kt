package com.jota.link.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Bundle
import android.util.Base64
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
import androidx.core.content.ContextCompat
import com.jota.link.audio.AudioHelper
import com.jota.link.network.BridgeClient
import com.jota.link.service.JotaBridgeService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

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

        setContent {
            MaterialTheme(
                colorScheme = darkColorScheme(
                    primary = Color(0xFFCBA6F7),
                    primaryContainer = Color(0xFF313244),
                    secondary = Color(0xFF89B4FA),
                    background = Color(0xFF1E1E2E),
                    surface = Color(0xFF181825),
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

    private fun startBridgeService() {
        val intent = Intent(this, JotaBridgeService::class.java).apply {
            putExtra("baseUrl", serverUrl)
            putExtra("apiKey", apiKey)
            putExtra("deviceId", deviceId)
        }
        startForegroundService(intent)
    }

    private fun updateConnectionConfig(newUrl: String, newKey: String, newId: String) {
        serverUrl = newUrl.trim()
        apiKey = newKey.trim()
        deviceId = newId.trim()

        prefs.edit().apply {
            putString("server_url", serverUrl)
            putString("api_key", apiKey)
            putString("device_id", deviceId)
            apply()
        }

        bridgeClient?.disconnect()
        bridgeClient = BridgeClient(this, serverUrl, apiKey, deviceId)
        startBridgeService()
        Toast.makeText(this, "Ajustes guardados. Reconectando...", Toast.LENGTH_SHORT).show()
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
                        isOnline = true
                    }
                } catch (e: Exception) {
                    activeWindowText = "Fallo al conectar"
                    isOnline = false
                }
            }
        }

        fun playAudioResponse(resp: JSONObject?) {
            if (resp == null) return
            val audioB64 = resp.optString("audio_base64", "")
            if (audioB64.isNotEmpty()) {
                scope.launch {
                    try {
                        val audioBytes = Base64.decode(audioB64, Base64.DEFAULT)
                        audioHelper.playAudio(audioBytes)
                    } catch (e: Exception) {
                        e.printStackTrace()
                    }
                }
            } else {
                val audioId = resp.optString("audio_id", "")
                if (audioId.isNotEmpty()) {
                    scope.launch {
                        try {
                            val audioBytes = bridgeClient?.downloadAudio(audioId)
                            if (audioBytes != null && audioBytes.isNotEmpty()) {
                                audioHelper.playAudio(audioBytes)
                            }
                        } catch (e: Exception) {
                            e.printStackTrace()
                        }
                    }
                }
            }
        }

        Scaffold(
            topBar = {
                TopAppBar(
                    title = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("Jota", fontWeight = FontWeight.Bold, fontSize = 22.sp)
                            Spacer(modifier = Modifier.width(10.dp))
                            Box(
                                modifier = Modifier
                                    .size(10.dp)
                                    .clip(CircleShape)
                                    .background(if (isOnline) Color(0xFFA6E3A1) else Color(0xFFF38BA8))
                            )
                        }
                    },
                    actions = {
                        TextButton(onClick = { showHelpDialog = true }) {
                            Text("Comandos", color = MaterialTheme.colorScheme.secondary)
                        }
                        TextButton(onClick = { showSettings = !showSettings }) {
                            Text(if (showSettings) "Cerrar" else "Ajustes", color = MaterialTheme.colorScheme.primary)
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface)
                )
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
                // ── Panel Desplegable de Ajustes ──
                AnimatedVisibility(visible = showSettings) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = Color(0xFF313244)),
                        shape = RoundedCornerShape(16.dp)
                    ) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text("Conexion Tailscale", fontWeight = FontWeight.SemiBold)
                            OutlinedTextField(
                                value = inputUrl,
                                onValueChange = { inputUrl = it },
                                label = { Text("Server URL") },
                                modifier = Modifier.fillMaxWidth()
                            )
                            OutlinedTextField(
                                value = inputKey,
                                onValueChange = { inputKey = it },
                                label = { Text("API Key") },
                                modifier = Modifier.fillMaxWidth()
                            )
                            OutlinedTextField(
                                value = inputId,
                                onValueChange = { inputId = it },
                                label = { Text("Device ID") },
                                modifier = Modifier.fillMaxWidth()
                            )
                            Button(
                                onClick = {
                                    updateConnectionConfig(inputUrl, inputKey, inputId)
                                    showSettings = false
                                },
                                modifier = Modifier.align(Alignment.End)
                            ) {
                                Text("Guardar y Conectar")
                            }
                        }
                    }
                }

                // ── Seccion 1: Boton de Voz Push-to-Talk ──
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF24273A)),
                    shape = RoundedCornerShape(24.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = if (isRecording) "Escuchando... suelta para procesar" else "Manten pulsado para hablar",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Medium,
                            color = if (isRecording) Color(0xFFF9E2AF) else Color(0xFFCAD3F5)
                        )
                        Spacer(modifier = Modifier.height(18.dp))

                        // Boton circular principal
                        Box(
                            contentAlignment = Alignment.Center,
                            modifier = Modifier
                                .size(130.dp)
                                .clip(CircleShape)
                                .background(if (isRecording) Color(0xFFF38BA8) else Color(0xFFCBA6F7))
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
                                                    lastPromptText = resp?.optString("prompt", "") ?: ""
                                                    replyText = resp?.optString("response_text", "Sin respuesta") ?: ""
                                                    isOnline = true
                                                    refreshPcStatus()
                                                    playAudioResponse(resp)
                                                } catch (e: Exception) {
                                                    replyText = "Fallo de conexion: ${e.message}"
                                                    isOnline = false
                                                }
                                            }
                                        }
                                    )
                                }
                        ) {
                            Text(
                                text = if (isRecording) "Soltar" else "Hablar",
                                color = Color(0xFF11111B),
                                fontWeight = FontWeight.Bold,
                                fontSize = 18.sp
                            )
                        }

                        // ── Seccion 2: Entrada de Texto para Peticiones ──
                        Spacer(modifier = Modifier.height(18.dp))
                        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            OutlinedTextField(
                                value = textChatInput,
                                onValueChange = { textChatInput = it },
                                placeholder = { Text("Escribe una peticion al PC...") },
                                modifier = Modifier.weight(1f),
                                maxLines = 1,
                                shape = RoundedCornerShape(12.dp)
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
                                                val resp = bridgeClient?.askText(prompt, generateAudio = true, playOnPc = true)
                                                replyText = resp?.optString("response_text", "") ?: ""
                                                isOnline = true
                                                refreshPcStatus()
                                                playAudioResponse(resp)
                                            } catch (e: Exception) {
                                                replyText = "Error: ${e.message}"
                                            }
                                        }
                                    }
                                },
                                shape = RoundedCornerShape(12.dp)
                            ) {
                                Text("Enviar")
                            }
                        }

                        // Globo de respuesta
                        if (lastPromptText.isNotEmpty() || replyText.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(14.dp))
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(Color(0xFF181825), RoundedCornerShape(14.dp))
                                    .padding(14.dp)
                            ) {
                                if (lastPromptText.isNotEmpty()) {
                                    Text("Tu: $lastPromptText", fontSize = 13.sp, color = Color(0xFFA6ADC8))
                                }
                                if (replyText.isNotEmpty()) {
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Text("Jota: $replyText", fontSize = 15.sp, fontWeight = FontWeight.Medium, color = Color(0xFF89B4FA))
                                }
                            }
                        }
                    }
                }

                // ── Seccion 3: Tarjeta de Estado del PC ──
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF24273A)),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Column(modifier = Modifier.padding(18.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text("Estado del PC", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                OutlinedButton(
                                    onClick = { openScreenshotsGallery() },
                                    shape = RoundedCornerShape(10.dp)
                                ) {
                                    Text("Capturas")
                                }
                                Button(
                                    onClick = { refreshPcStatus() },
                                    shape = RoundedCornerShape(10.dp)
                                ) {
                                    Text("Actualizar")
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(12.dp))
                        Text("Ventana activa: $activeWindowText", fontSize = 13.sp, color = Color(0xFFCAD3F5))

                        Spacer(modifier = Modifier.height(10.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text("Carga CPU", fontSize = 12.sp, color = Color(0xFFA6ADC8))
                            Text("$cpuLoad", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                        }

                        Spacer(modifier = Modifier.height(8.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text("Memoria RAM", fontSize = 12.sp, color = Color(0xFFA6ADC8))
                            Text("${memPct.toInt()}%", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                        }
                        LinearProgressIndicator(
                            progress = { (memPct / 100.0).toFloat().coerceIn(0f, 1f) },
                            modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp))
                        )

                        Spacer(modifier = Modifier.height(8.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text("Disco Principal", fontSize = 12.sp, color = Color(0xFFA6ADC8))
                            Text("${diskPct.toInt()}%", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                        }
                        LinearProgressIndicator(
                            progress = { (diskPct / 100.0).toFloat().coerceIn(0f, 1f) },
                            modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp))
                        )
                    }
                }
            }

            // ── Modal de Capturas de Pantalla del PC (Historial y Captura) ──
            if (showScreenshotDialog) {
                AlertDialog(
                    onDismissRequest = { showScreenshotDialog = false },
                    title = {
                        Column {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text("Capturas del PC", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                                OutlinedButton(
                                    onClick = { captureNewScreenshotNow() },
                                    enabled = !isScreenshotLoading,
                                    shape = RoundedCornerShape(8.dp),
                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)
                                ) {
                                    Text("Capturar ahora", fontSize = 11.sp)
                                }
                            }
                            if (screenshotsList.isNotEmpty()) {
                                val currentItem = screenshotsList.getOrNull(currentScreenshotIndex)
                                val dateStr = currentItem?.optString("date_str", "") ?: ""
                                val fname = currentItem?.optString("filename", "") ?: ""
                                Spacer(modifier = Modifier.height(4.dp))
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text(
                                        "${currentScreenshotIndex + 1} de ${screenshotsList.size}",
                                        fontSize = 12.sp,
                                        color = MaterialTheme.colorScheme.primary,
                                        fontWeight = FontWeight.SemiBold
                                    )
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
                                        .clip(RoundedCornerShape(10.dp))
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
                                    Button(
                                        onClick = {
                                            if (currentScreenshotIndex < screenshotsList.size - 1) {
                                                loadScreenshotAtIndex(currentScreenshotIndex + 1)
                                            }
                                        },
                                        enabled = !isScreenshotLoading && currentScreenshotIndex < screenshotsList.size - 1,
                                        shape = RoundedCornerShape(8.dp),
                                        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                                    ) {
                                        Text("< Anterior", fontSize = 11.sp)
                                    }
                                    Button(
                                        onClick = {
                                            if (currentScreenshotIndex > 0) {
                                                loadScreenshotAtIndex(currentScreenshotIndex - 1)
                                            }
                                        },
                                        enabled = !isScreenshotLoading && currentScreenshotIndex > 0,
                                        shape = RoundedCornerShape(8.dp),
                                        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                                    ) {
                                        Text("Siguiente >", fontSize = 11.sp)
                                    }
                                }

                                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                    TextButton(
                                        onClick = { saveCurrentScreenshotToPhone() },
                                        enabled = currentScreenshotBitmap != null
                                    ) {
                                        Text("Guardar", fontSize = 12.sp)
                                    }
                                    TextButton(onClick = { showScreenshotDialog = false }) {
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
                    title = { Text("Comandos Disponibles", fontWeight = FontWeight.Bold) },
                    text = {
                        Column(
                            modifier = Modifier.verticalScroll(rememberScrollState()),
                            verticalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            Text("Todos ejecutables mediante la voz o texto:", fontSize = 13.sp)

                            Text("Multimedia y Audio", fontWeight = FontWeight.SemiBold, color = Color(0xFFCBA6F7))
                            Text("- sube / baja el volumen\n- silencia el audio / quita silencio\n- pausa la musica / reproduce\n- siguiente cancion / cancion anterior", fontSize = 12.sp)

                            Text("Control del PC y Escritorios", fontWeight = FontWeight.SemiBold, color = Color(0xFF89B4FA))
                            Text("- bloquea el PC / suspende el equipo\n- cierra la ventana activa\n- pasa al escritorio [1-9]\n- mueve la ventana al escritorio [1-9]\n- haz una captura de pantalla\n- ¿como esta el PC?", fontSize = 12.sp)

                            Text("Telefono Vinculado", fontWeight = FontWeight.SemiBold, color = Color(0xFFF9E2AF))
                            Text("- encuentra mi movil / haz sonar mi telefono\n- ¿cuanta bateria le queda al movil?\n- enciende / apaga la linterna del movil\n- pon el movil en silencio\n- manda al movil la ultima captura\n- manda al movil el archivo [nombre]\n- envia al movil este enlace https://...", fontSize = 12.sp)

                            Text("Utilidades y Asistente", fontWeight = FontWeight.SemiBold, color = Color(0xFFA6E3A1))
                            Text("- ¿que tiempo hace en [ciudad]? / ¿va a llover hoy?\n- anota [tarea o nota]\n- ¿que notas tengo pendientes?\n- avisame en [X] minutos para [motivo]\n- abre [aplicacion] / buscame en la web [consulta]", fontSize = 12.sp)
                        }
                    },
                    confirmButton = {
                        Button(onClick = { showHelpDialog = false }) {
                            Text("Entendido")
                        }
                    }
                )
            }
        }
    }
}
