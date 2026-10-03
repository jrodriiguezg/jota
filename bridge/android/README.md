# JotaLink — Aplicacion Android para Jota Bridge

Aplicacion companera para Android que conecta tu telefono con tu PC (Jota) a traves de una red privada **Tailscale**.

---

## Funcionalidades

1. **Invocacion de Voz y Texto (Push-to-Talk):**
   - Manten pulsado el boton de microfono para hablar con Jota desde cualquier lugar con conexion Tailscale.
   - Jota procesa la voz con Whisper, ejecuta el razonamiento con Qwen3 y Piper sintetiza la voz que suena directamente en los altavoces de tu movil.

2. **Control y Consultas del PC:**
   - **Estado en tiempo real:** Uso de CPU, memoria RAM, espacio en disco, ventana activa de Hyprland y uptime.
   - **Captura de Pantalla remota:** Toma una captura en Wayland (`grim`) y la muestra en la pantalla del telefono al instante.
   - **Sincronizacion de Portapapeles:** Lee el portapapeles del PC o envia texto directamente al portapapeles de Wayland (`wl-copy` / `wl-paste`).
   - **Descarga de Archivos:** Descarga cualquier archivo permitido del PC indicando su ruta.

3. **Control del Telefono desde el PC por Voz:**
   - *"Jota, encuentra mi movil"* -> El telefono suena al maximo volumen en el canal de alarma (incluso en silencio o no molestar) y vibra de forma continua hasta ser descartado.
   - *"Jota, ¿cuanta bateria le queda al movil?"* -> El PC consulta el estado reportado y te responde por voz.
   - *"Jota, envia este enlace a mi movil"* -> El telefono abre automaticamente la URL en tu navegador habitual.
   - *"Jota, copia esto a mi movil"* -> Se guarda directamente en el portapapeles de Android.

---

## Arquitectura Tecnica Android

- **Canal Persistente (`JotaBridgeService`):**
  Un servicio Foreground Service con notificacion permanente mantiene abierta una conexion WebSocket (`/ws/phone`) con el PC a traves de Tailscale.
  Esto garantiza que el PC siempre pueda enviar comandos instantaneos (`ring`, `clipboard`, `open_url`) sin necesidad de servidores HTTP en Android ni puertos abiertos.
- **Audio Recorder (`AudioRecorder`):**
  Graba audio PCM mono a 16 kHz (el formato nativo esperado por `whisper.cpp`).
- **Alarma en Modo Silencio (`AudioManager.STREAM_ALARM`):**
  Utiliza el canal de audio del sistema reservado para alarmas, el cual sobrepasa el modo silencioso o no molestar del terminal.

---

## Configuracion y Parametros

En la pantalla de Ajustes de la aplicacion configura:

1. **Servidor Tailscale:**
   - IP de Tailscale de tu PC (ejemplo: `http://100.x.y.z:8765` o `http://pc-jota:8765`).
2. **API Key:**
   - Clave precompartida definida en el PC (`JOTA_BRIDGE_API_KEY`, por defecto `jota-secret-tailscale-key`).
3. **ID de Dispositivo:**
   - Nombre identificativo para tu telefono (ejemplo: `pixel8_jota`).

---

## Permisos Requeridos en Android

- `android.permission.RECORD_AUDIO`: Para grabar voz en el modo Push-to-Talk.
- `android.permission.INTERNET`: Comunicacion con el PC via Tailscale.
- `android.permission.VIBRATE`: Vibracion al sonar la alarma de localizacion.
- `android.permission.POST_NOTIFICATIONS`: Notificaciones del servicio en segundo plano (Android 13+).
- `android.permission.FOREGROUND_SERVICE` & `FOREGROUND_SERVICE_DATA_SYNC`: Mantener el WebSocket activo con pantalla apagada.
