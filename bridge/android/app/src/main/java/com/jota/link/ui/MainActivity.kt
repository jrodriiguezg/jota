package com.jota.link.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Bundle
import android.os.Environment
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.jota.link.audio.AudioHelper
import com.jota.link.network.BridgeClient
import com.jota.link.service.JotaBridgeService
import kotlinx.coroutines.launch
import java.io.File

class MainActivity : ComponentActivity() {
    private val audioHelper = AudioHelper()
    private lateinit var bridgeClient: BridgeClient

    private var serverUrl by mutableStateOf("http://100.64.0.1:8765")
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
        bridgeClient = BridgeClient(this, serverUrl, apiKey, deviceId)

        checkPermissions()

        setContent {
            MaterialTheme {
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

    @OptIn(ExperimentalMaterial3Api::class)
    @Composable
    fun JotaLinkScreen() {
        val scope = rememberCoroutineScope()
        var pcStatusText by remember { mutableStateOf("Sin consultar") }
        var isRecording by remember { mutableStateOf(false) }
        var replyText by remember { mutableStateOf("") }
        var screenshotBitmap by remember { mutableStateOf<android.graphics.Bitmap?>(null) }
        var filePathInput by remember { mutableStateOf("/home/user/documento.txt") }
        var clipboardInput by remember { mutableStateOf("") }

        Scaffold(
            topBar = {
                TopAppBar(title = { Text("JotaLink — Control PC") })
            }
        ) { padding ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(16.dp)
                    .verticalScroll(rememberScrollState()),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // 1. Tarjeta Push-to-Talk
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = if (isRecording) "Escuchando... suelta para enviar" else "Manten pulsado para hablar con Jota",
                            style = MaterialTheme.typography.titleMedium
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Button(
                            onClick = {},
                            modifier = Modifier
                                .size(90.dp)
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
                                                    val resp = bridgeClient.askVoice(wavBytes)
                                                    replyText = resp.optString("response_text", "Sin respuesta")
                                                } catch (e: Exception) {
                                                    replyText = "Error: ${e.message}"
                                                }
                                            }
                                        }
                                    )
                                }
                        ) {
                            Text(if (isRecording) "Grabando" else "Hablar")
                        }
                        if (replyText.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(8.dp))
                            Text("Jota: $replyText", style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }

                // 2. Monitor del PC
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("Estado del PC", style = MaterialTheme.typography.titleMedium)
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(pcStatusText, style = MaterialTheme.typography.bodySmall)
                        Spacer(modifier = Modifier.height(8.dp))
                        Button(onClick = {
                            scope.launch {
                                try {
                                    val status = bridgeClient.getPcStatus()
                                    val cpu = status.optJSONObject("cpu")?.optDouble("load_1m", 0.0) ?: 0.0
                                    val mem = status.optJSONObject("memory")?.optDouble("percent_used", 0.0) ?: 0.0
                                    val disk = status.optJSONObject("disk")?.optDouble("percent_used", 0.0) ?: 0.0
                                    val win = status.optJSONObject("active_window")?.optString("class", "Desconocida") ?: ""
                                    pcStatusText = "CPU: $cpu | RAM: $mem% | Disco: $disk%\nVentana Hyprland: $win"
                                } catch (e: Exception) {
                                    pcStatusText = "Error conectando: ${e.message}"
                                }
                            }
                        }) {
                            Text("Actualizar Estado")
                        }
                    }
                }

                // 3. Captura de Pantalla
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("Captura de Pantalla del PC", style = MaterialTheme.typography.titleMedium)
                        Spacer(modifier = Modifier.height(8.dp))
                        Button(onClick = {
                            scope.launch {
                                try {
                                    val bytes = bridgeClient.getPcScreenshot()
                                    if (bytes.isNotEmpty()) {
                                        screenshotBitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                                    }
                                } catch (e: Exception) {
                                    Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                                }
                            }
                        }) {
                            Text("Ver Pantalla")
                        }
                        screenshotBitmap?.let { bmp ->
                            Spacer(modifier = Modifier.height(12.dp))
                            Image(
                                bitmap = bmp.asImageBitmap(),
                                contentDescription = "Captura PC",
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(200.dp)
                            )
                        }
                    }
                }

                // 4. Portapapeles y Enlaces
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("Portapapeles del PC", style = MaterialTheme.typography.titleMedium)
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedTextField(
                            value = clipboardInput,
                            onValueChange = { clipboardInput = it },
                            label = { Text("Texto a enviar al PC") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = {
                                scope.launch {
                                    try {
                                        val ok = bridgeClient.setPcClipboard(clipboardInput)
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
                                        val text = bridgeClient.getPcClipboard()
                                        clipboardInput = text
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

                // 5. Descarga de Archivos
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("Descargar Archivo del PC", style = MaterialTheme.typography.titleMedium)
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedTextField(
                            value = filePathInput,
                            onValueChange = { filePathInput = it },
                            label = { Text("Ruta en el PC") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Button(onClick = {
                            scope.launch {
                                try {
                                    val fileName = File(filePathInput).name
                                    val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                                    val dest = File(downloadsDir, fileName)
                                    val ok = bridgeClient.downloadPcFile(filePathInput, dest)
                                    Toast.makeText(
                                        this@MainActivity,
                                        if (ok) "Descargado en Descargas/$fileName" else "Fallo en descarga",
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
