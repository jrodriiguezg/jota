package com.jota.link.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Bundle
import android.os.Environment
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.jota.link.audio.AudioHelper
import com.jota.link.network.BridgeClient
import com.jota.link.service.JotaBridgeService
import kotlinx.coroutines.launch
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

        var screenshotBitmap by remember { mutableStateOf<android.graphics.Bitmap?>(null) }
        var filePathInput by remember { mutableStateOf("/home/jrodriiguezg/README.md") }
        var clipboardInput by remember { mutableStateOf("") }

        var showSettings by remember { mutableStateOf(false) }
        var inputUrl by remember { mutableStateOf(serverUrl) }
        var inputKey by remember { mutableStateOf(apiKey) }
        var inputId by remember { mutableStateOf(deviceId) }

        // Funcion para ejecutar acciones rapidas en el PC
        fun runPcAction(action: String) {
            scope.launch {
                try {
                    val (ok, msg) = bridgeClient?.executePcAction(action) ?: Pair(false, "No cliente")
                    Toast.makeText(this@MainActivity, if (ok) msg else "Error: $msg", Toast.LENGTH_SHORT).show()
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Fallo: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }

        Scaffold(
            topBar = {
                TopAppBar(
                    title = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("JotaLink", fontWeight = FontWeight.Bold, fontSize = 20.sp)
                            Spacer(modifier = Modifier.width(8.dp))
                            Box(
                                modifier = Modifier
                                    .size(10.dp)
                                    .clip(CircleShape)
                                    .background(if (isOnline) Color(0xFFA6E3A1) else Color(0xFFF38BA8))
                            )
                        }
                    },
                    actions = {
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
                    .padding(14.dp)
                    .verticalScroll(rememberScrollState()),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(14.dp)
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
                            Text("Configuracion de Conexion", fontWeight = FontWeight.SemiBold)
                            OutlinedTextField(
                                value = inputUrl,
                                onValueChange = { inputUrl = it },
                                label = { Text("Server URL (Tailscale)") },
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

                // ── Seccion 1: Push-to-Talk y Conversacion ──
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF24273A)),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(18.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = if (isRecording) "Escuchando... suelta para procesar" else "Manten pulsado para hablar",
                            style = MaterialTheme.typography.titleMedium,
                            color = if (isRecording) Color(0xFFF9E2AF) else Color(0xFFCAD3F5)
                        )
                        Spacer(modifier = Modifier.height(14.dp))

                        // Boton circular principal
                        Box(
                            contentAlignment = Alignment.Center,
                            modifier = Modifier
                                .size(110.dp)
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
                                text = if (isRecording) "Sueltalo" else "Voz",
                                color = Color(0xFF11111B),
                                fontWeight = FontWeight.Bold,
                                fontSize = 16.sp
                            )
                        }

                        // Cuadro de texto para preguntas escritas
                        Spacer(modifier = Modifier.height(14.dp))
                        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            OutlinedTextField(
                                value = textChatInput,
                                onValueChange = { textChatInput = it },
                                placeholder = { Text("O escribe una peticion...") },
                                modifier = Modifier.weight(1f),
                                maxLines = 1
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Button(onClick = {
                                if (textChatInput.isNotBlank()) {
                                    val prompt = textChatInput
                                    textChatInput = ""
                                    scope.launch {
                                        try {
                                            lastPromptText = prompt
                                            replyText = "Consultando a Jota..."
                                            val resp = bridgeClient?.askText(prompt)
                                            replyText = resp?.optString("response_text", "") ?: ""
                                            isOnline = true
                                        } catch (e: Exception) {
                                            replyText = "Error: ${e.message}"
                                        }
                                    }
                                }
                            }) {
                                Text("Enviar")
                            }
                        }

                        if (lastPromptText.isNotEmpty() || replyText.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(12.dp))
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(Color(0xFF181825), RoundedCornerShape(12.dp))
                                    .padding(12.dp)
                            ) {
                                if (lastPromptText.isNotEmpty()) {
                                    Text("Tu: $lastPromptText", fontSize = 13.sp, color = Color(0xFFA6ADC8))
                                }
                                if (replyText.isNotEmpty()) {
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Text("Jota: $replyText", fontSize = 14.sp, fontWeight = FontWeight.Medium, color = Color(0xFF89B4FA))
                                }
                            }
                        }
                    }
                }

                // ── Seccion 2: Acciones Rapidas del PC ──
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF24273A)),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("Acciones Rapidas del PC", fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.height(10.dp))

                        // Fila 1: Multimedia
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = { runPcAction("play_pause") }, modifier = Modifier.weight(1f)) {
                                Text("Play / Pausa", fontSize = 12.sp)
                            }
                            Button(onClick = { runPcAction("next") }, modifier = Modifier.weight(1f)) {
                                Text("Siguiente", fontSize = 12.sp)
                            }
                            Button(onClick = { runPcAction("mute") }, modifier = Modifier.weight(1f)) {
                                Text("Silencio", fontSize = 12.sp)
                            }
                        }
                        Spacer(modifier = Modifier.height(8.dp))

                        // Fila 2: Volumen y Seguridad
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = { runPcAction("vol_up") }, modifier = Modifier.weight(1f)) {
                                Text("Volumen +", fontSize = 12.sp)
                            }
                            Button(onClick = { runPcAction("vol_down") }, modifier = Modifier.weight(1f)) {
                                Text("Volumen -", fontSize = 12.sp)
                            }
                            Button(
                                onClick = { runPcAction("lock") },
                                modifier = Modifier.weight(1f),
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFF38BA8), contentColor = Color(0xFF11111B))
                            ) {
                                Text("Bloquear", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }

                // ── Seccion 3: Monitor del PC en Tiempo Real ──
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF24273A)),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text("Monitor del PC", fontWeight = FontWeight.Bold)
                            Button(onClick = {
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
                                        activeWindowText = "Fallo al consultar"
                                        isOnline = false
                                    }
                                }
                            }) {
                                Text("Actualizar")
                            }
                        }

                        Spacer(modifier = Modifier.height(10.dp))
                        Text("Ventana activa: $activeWindowText", fontSize = 13.sp, color = Color(0xFFCAD3F5))

                        Spacer(modifier = Modifier.height(8.dp))
                        Text("Memoria RAM: ${memPct.toInt()}%", fontSize = 12.sp)
                        LinearProgressIndicator(
                            progress = { (memPct / 100.0).toFloat().coerceIn(0f, 1f) },
                            modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp))
                        )

                        Spacer(modifier = Modifier.height(8.dp))
                        Text("Disco Principal: ${diskPct.toInt()}%", fontSize = 12.sp)
                        LinearProgressIndicator(
                            progress = { (diskPct / 100.0).toFloat().coerceIn(0f, 1f) },
                            modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp))
                        )
                    }
                }

                // ── Seccion 4: Captura de Pantalla Wayland ──
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF24273A)),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text("Captura de Pantalla", fontWeight = FontWeight.Bold)
                            Button(onClick = {
                                scope.launch {
                                    try {
                                        val bytes = bridgeClient?.getPcScreenshot()
                                        if (bytes != null && bytes.isNotEmpty()) {
                                            screenshotBitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                                            isOnline = true
                                        }
                                    } catch (e: Exception) {
                                        Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            }) {
                                Text("Capturar")
                            }
                        }

                        screenshotBitmap?.let { bmp ->
                            Spacer(modifier = Modifier.height(12.dp))
                            Image(
                                bitmap = bmp.asImageBitmap(),
                                contentDescription = "Captura PC",
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(210.dp)
                                    .clip(RoundedCornerShape(12.dp))
                            )
                        }
                    }
                }

                // ── Seccion 5: Sincronizador de Portapapeles ──
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF24273A)),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("Portapapeles del PC", fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedTextField(
                            value = clipboardInput,
                            onValueChange = { clipboardInput = it },
                            label = { Text("Texto a enviar al PC") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(10.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = {
                                scope.launch {
                                    try {
                                        val ok = bridgeClient?.setPcClipboard(clipboardInput) ?: false
                                        Toast.makeText(this@MainActivity, if (ok) "Copiado al PC" else "Error", Toast.LENGTH_SHORT).show()
                                    } catch (e: Exception) {
                                        Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            }) {
                                Text("Enviar al PC")
                            }
                            Button(onClick = {
                                scope.launch {
                                    try {
                                        val text = bridgeClient?.getPcClipboard() ?: ""
                                        clipboardInput = text
                                        Toast.makeText(this@MainActivity, "Portapapeles leido", Toast.LENGTH_SHORT).show()
                                    } catch (e: Exception) {
                                        Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            }) {
                                Text("Leer del PC")
                            }
                        }
                    }
                }

                // ── Seccion 6: Descarga de Archivos del PC ──
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF24273A)),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("Descargar Archivo del PC", fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedTextField(
                            value = filePathInput,
                            onValueChange = { filePathInput = it },
                            label = { Text("Ruta en el PC") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(10.dp))
                        Button(onClick = {
                            scope.launch {
                                try {
                                    val fileName = File(filePathInput).name
                                    val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                                    val dest = File(downloadsDir, fileName)
                                    val ok = bridgeClient?.downloadPcFile(filePathInput, dest) ?: false
                                    Toast.makeText(
                                        this@MainActivity,
                                        if (ok) "Descargado en Descargas/$fileName" else "Fallo al descargar archivo",
                                        Toast.LENGTH_LONG
                                    ).show()
                                } catch (e: Exception) {
                                    Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                                }
                            }
                        }) {
                            Text("Descargar al Movil")
                        }
                    }
                }
            }
        }
    }
}
