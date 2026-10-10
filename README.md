# Jota — Asistente de Voz Local y Ecosistema Multi-Dispositivo

Jota es un asistente de voz autonomo, multimodal y completamente offline disenado para Linux bajo Wayland (Hyprland). Permite controlar el sistema operativo, gestionar ventanas, automatizar tareas mediante escenas YAML, sincronizar y controlar dispositivos moviles (Android), emitir contenido a Smart TVs (Chromecast y ADB), utilizar tablets como segunda pantalla y disfrutar de reproduccion musical inteligente con Navidrome.

---

## Indice

- [Arquitectura del Sistema](#arquitectura-del-sistema)
- [Capacidades Principales](#capacidades-principales)
  - [1. Razonamiento Local y Tool Calling con Qwen2.5-1.5B](#1-razonamiento-local-y-tool-calling-con-qwen25-15b)
  - [2. Escenas y Rutinas Configurables en YAML](#2-escenas-y-rutinas-configurables-en-yaml)
  - [3. Resolucion de Contexto Implicito](#3-resolucion-de-contexto-implicito)
  - [4. Emision a Smart TV y Control HDMI-CEC](#4-emision-a-smart-tv-y-control-hdmi-cec)
  - [5. Streaming de Pantallas, scrcpy y Monitores Virtuales](#5-streaming-de-pantallas-scrcpy-y-monitores-virtuales)
  - [6. Navidrome, Smart Radio y Handoff Multimedia](#6-navidrome-smart-radio-y-handoff-multimedia)
  - [7. Jota Bridge y Vinculacion Android](#7-jota-bridge-y-vinculacion-android)
  - [8. Menu Contextual de Dolphin (KDE Service Menu)](#8-menu-contextual-de-dolphin-kde-service-menu)
- [Catalogo de Herramientas y Comandos](#catalogo-de-herramientas-y-comandos)
- [Requisitos del Sistema](#requisitos-del-sistema)
- [Instalacion Paso a Paso](#instalacion-paso-a-paso)
- [Configuracion](#configuracion)
- [Ejecucion como Servicio Systemd](#ejecucion-como-servicio-systemd)
- [Consultar Registros con Journalctl](#consultar-registros-con-journalctl)
- [Bateria de Pruebas](#bateria-de-pruebas)
- [Solucion de Problemas](#solucion-de-problemas)

---

## Arquitectura del Sistema

Jota funciona mediante una arquitectura desacoplada de alto rendimiento:

| Componente | Tecnologia / Herramienta | Descripcion |
|---|---|---|
| Reconocimiento de Voz (STT) | [`whisper.cpp`](https://github.com/ggerganov/whisper.cpp) (`whisper-cli`) | Modelo `ggml-small.bin`. Transcripcion local de alta precision en espanol. |
| Razonamiento e Inferencia (LLM) | [`llama-cpp-python`](https://github.com/abetlen/llama-cpp-python) | Modelo `qwen2.5-1.5b-instruct-q4_k_m.gguf` (1.5B parametros). Formato ChatML nativo. |
| Sintesis de Voz (TTS) | [`piper-tts`](https://github.com/rhasspy/piper) | Voz neuronal `es_ES-sharvard-medium.onnx` ejecutada de forma local e instantanea. |
| Enrutador de Intenciones | Enrutador hibrido de dos etapas | 1) Evaluacion por regex ultra-rapida (<10ms) para comandos frecuentes; 2) Fallback al LLM para deduccion contextual y tool calling estructurado. |
| Orbe Visual | GTK4 / Layer Shell | Ventana de capa Wayland que muestra el estado de Jota en tiempo real (escucha, pensamiento, habla). |
| Servidor Bridge y API | FastAPI + Uvicorn + WebSockets | Canal de comunicacion LAN con mDNS (ZeroConf) y reenvio ADB para dispositivos Android. |
| Audio y Composicion | PipeWire / WirePlumber / Hyprland | Control directo de volumen (`wpctl`), reproduccion MPRIS (`playerctl`) y capturas (`grim`). |

---

## Capacidades Principales

### 1. Razonamiento Local y Tool Calling con Qwen2.5-1.5B

Jota utiliza el modelo **Qwen2.5-1.5B-Instruct** cuantizado a 4 bits (`qwen2.5-1.5b-instruct-q4_k_m.gguf`):
- **Baja latencia:** Inferencia acotada a 4 hilos de CPU con tiempos de respuesta inferiores a 1 segundo.
- **Modo Non-Thinking:** Configurado por defecto (`/no_think`) para evitar latencias innecesarias de razonamiento interno antes de emitir la orden.
- **Formato de ejecucion estricto:** El modelo emite directivas en formato `TOOL: nombre_herramienta(parametro='...')` seguidas de una confirmacion breve. El sintetizador de voz lee exclusivamente el mensaje hablado, aislando la orden tecnica.
- **Push-to-Talk (Tecla Copilot):** Al pulsar la tecla Copilot, Jota graba el audio mientras se mantiene presionada y lo procesa al soltarla. El modo manos libres continuo se encuentra desactivado por defecto para evitar transcripciones innecesarias de ruido ambiental.

### 2. Escenas y Rutinas Configurables en YAML

El motor de escenas ([`jota/tools/scenes.py`](file:///home/jrodriiguezg/Documentos/Proyectos/hyper/jota/jota/tools/scenes.py)) permite disparar secuencias de herramientas mediante un archivo de configuracion en `~/.config/jota/scenes.yaml`. Si el archivo no existe, Jota genera una configuracion inicial automatica:

- **Modo Cine (`modo_cine`):** Pone la ventana activa en pantalla completa, reduce el brillo al 20%, enciende el filtro nocturno y enciende la television por HDMI-CEC.
- **Modo Trabajo (`modo_trabajo`):** Ajusta el brillo al 80%, desactiva el filtro nocturno y cambia al espacio de trabajo 1.
- **Buenas Noches (`buenas_noches`):** Activa el modo noche, silencia el audio, apaga el televisor via HDMI-CEC y bloquea la sesion del PC.

### 3. Resolucion de Contexto Implicito

El modulo [`jota/tools/context.py`](file:///home/jrodriiguezg/Documentos/Proyectos/hyper/jota/jota/tools/context.py) evita que el usuario tenga que dictar URLs o parametros extensos por voz:
- Si el usuario dice *"manda esto a la tele"*, Jota inspecciona el portapapeles (`wl-paste`), la ventana activa de Hyprland (`hyprctl activewindow`) o la musica en reproduccion para obtener la URL o pista automaticamente.
- Resolucion de alias de dispositivos: Coloquialismos como *"tele"*, *"salon"*, *"television"*, *"tablet"* o *"movil"* se mapean a sus direcciones y metodos de control correspondientes.

### 4. Emision a Smart TV y Control HDMI-CEC

- **Casting de medios (`catt`):** Emite cualquier enlace de video o flujo multimedia hacia dispositivos Chromecast o Android TV.
- **Control de reproduccion:** Comandos para pausar, reanudar o detener el casteo en la tele.
- **Lanzamiento de aplicaciones en Android TV:** Mediante ADB por red (`adb -s <ip>:5555 shell monkey -p <paquete> 1`), Jota puede abrir directamente apps nativas como Netflix, Prime Video, YouTube, Plex, Kodi y Spotify.
- **HDMI-CEC (`cec-client`):** Enciende el televisor (*"enciende la tele"*), lo apaga (*"apaga la tele"*) o cambia la entrada HDMI activa al PC (*"cambia la entrada en la tele"*).

### 5. Streaming de Pantallas, scrcpy y Monitores Virtuales

- **Pantalla del movil en PC:** El comando *"muestra la pantalla del movil"* inicia `scrcpy` en una ventana independiente en Hyprland conectada por USB o Wi-Fi.
- **Pantalla virtual headless:** Jota crea salidas virtuales en Hyprland sobre la marcha mediante `hyprctl output create headless`.
- **Tablet como segunda pantalla:** El comando *"conecta la tablet"* inicializa una salida headless y expone la sesion mediante `wayvnc` en el puerto `5900`, permitiendo conectar cualquier tablet o cliente VNC como monitor extendido.

### 6. Navidrome, Smart Radio y Handoff Multimedia

- **Radio inteligente estilo Siri:** Al pedir *"pon una cancion de [artista]"* o *"reproduce [titulo]"*, Jota consulta la API Subsonic de Navidrome (`/rest/search3.view` y `/rest/getRandomSongs.view`) y construye una cola dinamica con pistas similares o del mismo genero.
- **Handoff al movil:** Al decir *"pasa la musica al movil"*, Jota pausa la reproduccion local en el PC, guarda la cola en el servidor y notifica a la app de Android con la URL directa y la posicion exacta en milisegundos para continuar la escucha sin interrupciones.
- **Marcar favorita:** Al decir *"marca esta cancion como favorita"*, Jota marca la pista en reproduccion en la base de datos de Navidrome via `/rest/star.view`.
- **Enviar musica a la tele:** El comando *"pon la musica en la tele"* transmite el flujo de audio de la pista activa a la television mediante `catt`.

### 7. Jota Bridge y Vinculacion Android

El servicio `jota-bridge` expone un servidor FastAPI y WebSocket en el puerto `8765`:
- **Descubrimiento automatico mDNS:** Anuncia el servicio en la red local (`_jota-bridge._tcp.local.`) para que la app de Android se conecte sin configurar IPs manualmente.
- **ADB Reverse automatico:** Si el telefono se conecta por cable USB, ejecuta `adb reverse tcp:8765 tcp:8765`, permitiendo comunicacion local inmediata a traves de `127.0.0.1:8765`.
- **Sincronizacion bidireccional:**
  - Control de linterna, timbrado de localizacion y nivel de bateria del telefono.
  - Pausa automatica de la musica del PC al recibir una llamada telefonica en Android.
  - Sincronizacion universal del portapapeles entre el PC y el movil.
  - Notificacion multimedia en Android con `MediaSession` y `Notification.MediaStyle`.

### 8. Menu Contextual de Dolphin (KDE Service Menu)

Instalado en `~/.local/share/kio/servicemenus/jota_send_to_phone.desktop`:
- Al hacer clic derecho sobre cualquier archivo o seleccion en Dolphin, aparece la opcion **"Enviar al movil con Jota"**.
- El archivo se transfiere de forma segura a traves de la API del Bridge directamente al telefono y muestra una notificacion de escritorio.

---

## Catalogo de Herramientas y Comandos

| Categoria | Ejemplos de Comandos por Voz | Herramienta Ejecutada |
|---|---|---|
| **Escenas** | "activa el modo cine", "modo trabajo", "buenas noches", "cuales son las escenas" | `trigger_scene`, `list_scenes` |
| **Smart TV & Cast** | "manda esto a la tele", "pausa la tele", "abre netflix en la tele" | `cast_media`, `cast_control`, `launch_tv_app` |
| **HDMI-CEC** | "enciende la tele", "apaga la tele", "cambia la entrada en la tele" | `cec_control` |
| **Streaming** | "muestra la pantalla del movil", "conecta la tablet", "desconecta la tablet" | `open_phone_screen`, `tablet_display` |
| **Navidrome** | "pon algo de Daft Punk", "marca esta cancion como favorita", "pasa la musica al movil" | `navidrome_play`, `favorite_song`, `media_handoff` |
| **Volumen** | "sube el volumen", "baja el volumen", "volumen al 70%", "silencia el audio" | `volume_control` |
| **Multimedia** | "pausa la musica", "reproduce", "siguiente cancion", "cancion anterior" | `media_control` |
| **Ventanas** | "pantalla completa", "haz flotante esta ventana", "cierra firefox", "cierra esta ventana" | `window_action`, `close_window` |
| **Escritorios** | "pasa al escritorio 2", "mueve la ventana al escritorio 3" | `switch_workspace`, `move_to_workspace` |
| **Pantalla PC** | "captura pantalla", "muestrame la pantalla del pc", "que error sale en la terminal" | `screenshot`, `analyze_screen` |
| **Iluminacion** | "sube el brillo", "brillo al 50%", "activa el modo noche", "quita la luz nocturna" | `brightness_control`, `night_mode_control` |
| **DevOps** | "que proceso usa el puerto 8080", "libera el puerto 3000", "contenedores activos", "top ram", "estado del repo" | `port_action`, `container_action`, `process_monitor`, `git_status` |
| **Movil** | "donde esta mi movil", "enciende la linterna del movil", "manda la url al movil" | `phone_control`, `phone_send_url` |
| **Sistema** | "bloquea el pc", "que hora es", "que tiempo hace en Madrid", "bateria del pc" | `lock_pc`, `get_current_time`, `get_weather`, `get_pc_battery` |

---

## Requisitos del Sistema

- **Sistema Operativo:** Fedora Linux 40+ (o distribuciones equivalentes basadas en Linux y Wayland).
- **Entorno de Escritorio:** Hyprland (Wayland compositor).
- **Audio:** PipeWire con WirePlumber.
- **Python:** 3.11 o superior.
- **Paquetes del sistema (instalables via dnf):**
  - Multimedia y Wayland: `grim`, `slurp`, `wl-clipboard`, `playerctl`, `brightnessctl`
  - Streaming y TV: `scrcpy`, `android-tools` (adb), `cec-client` (libcec), `wayvnc`
  - Filtro azul: `hyprsunset`
  - Red y utilidades: `socat`, `git`, `curl`
- **Permisos de entrada:** El usuario debe pertenecer al grupo `input` para leer eventos de la tecla Copilot sin privilegios root:
  ```bash
  sudo usermod -aG input $USER
  ```

---

## Instalacion Paso a Paso

### 1. Clonar el repositorio

```bash
git clone git@github.com:jrodriiguezg/jota.git
cd jota
git checkout bridge
```

### 2. Ejecutar instalacion automatica

El script `setup.sh` prepara el entorno virtual, compila `whisper-cli` y descarga los modelos iniciales:

```bash
bash setup.sh
```

### 3. Instalar herramientas de streaming y cast

Dentro del entorno virtual, instala las dependencias de emision:

```bash
source .venv/bin/activate
pip install catt pychromecast pyyaml
```

Instala las utilidades complementarias del sistema si deseas soporte para streaming y televisor:

```bash
sudo dnf install -y scrcpy wayvnc libcec
```

### 4. Descargar el modelo Qwen2.5-1.5B (Recomendado)

Si no lo tienes en tu directorio local de modelos:

```bash
mkdir -p ~/.local/share/jota/models/qwen
# Descarga directa del archivo GGUF (aprox. 1.1 GB):
curl -L -o ~/.local/share/jota/models/qwen/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf
```

---

## Configuracion

### Dispositivos Multi-Pantalla ([`jota/config.py`](file:///home/jrodriiguezg/Documentos/Proyectos/hyper/jota/jota/config.py))

Edita los alias de tus dispositivos en la variable `DEVICES`:

```python
DEVICES = {
    "tele": {"name": "Android TV Salón", "type": "cast", "adb": "192.168.1.50:5555"},
    "television": {"name": "Android TV Salón", "type": "cast", "adb": "192.168.1.50:5555"},
    "tablet": {"name": "Tablet", "type": "vnc", "host": "192.168.1.180"},
    "movil": {"name": "Teléfono", "type": "adb", "serial": "E6IBDMBEJBWCNZS8"},
}
```

### Escenas Personalizadas (`~/.config/jota/scenes.yaml`)

Puedes modificar o anadir cualquier escena YAML con secuencias de herramientas:

```yaml
scenes:
  modo_lectura:
    description: "Configuracion de bajo contraste para lectura prolongada"
    actions:
      - tool: brightness_control
        args: { percent: 40 }
      - tool: night_mode_control
        args: { action: on }
```

### Servidor Navidrome / Subsonic

Configura tus credenciales de Navidrome mediante variables de entorno o editando `jota/config.py`:

```bash
export NAVIDROME_URL="https://tu-servidor-navidrome.com"
export NAVIDROME_USER="tu_usuario"
export NAVIDROME_TOKEN="tu_token_subsonic"
export NAVIDROME_SALT="tu_salt_subsonic"
```

---

## Ejecucion como Servicio Systemd

Para que Jota arranque automaticamente con tu sesion de usuario de Linux y mantenga sus registros centralizados en `journalctl`, configuralo como un servicio de usuario de systemd.

### 1. Crear el archivo del servicio

Crea el archivo `~/.config/systemd/user/jota.service`:

```ini
[Unit]
Description=Jota - Asistente de Voz Local y Bridge Multi-Dispositivo
Documentation=https://github.com/jrodriiguezg/jota
After=network-online.target pipewire.service wireplumber.service
Wants=network-online.target pipewire.service wireplumber.service
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory=/home/jrodriiguezg/Documentos/Proyectos/hyper/jota
ExecStart=/home/jrodriiguezg/Documentos/Proyectos/hyper/jota/.venv/bin/jota-bridge
Restart=always
RestartSec=3
KillMode=control-group
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/home/jrodriiguezg/Documentos/Proyectos/hyper/jota/.venv/bin:/home/jrodriiguezg/.local/bin:/usr/local/bin:/usr/bin:/bin

# Gestion de registros en journalctl
StandardOutput=journal
StandardError=journal
SyslogIdentifier=jota

[Install]
WantedBy=default.target
```

### 2. Recargar y activar el servicio

```bash
systemctl --user daemon-reload
systemctl --user enable --now jota.service
```

### 3. Comprobar el estado del servicio

```bash
systemctl --user status jota.service
```

---

## Consultar Registros con Journalctl

Todos los registros de ejecucion, transcripciones y acciones de herramientas se almacenan de forma estructurada en journalctl.

- **Seguir logs en tiempo real:**
  ```bash
  journalctl --user -u jota -f
  ```

- **Ver los ultimos 50 mensajes de registro:**
  ```bash
  journalctl --user -u jota -n 50 --no-pager
  ```

- **Filtrar por errores:**
  ```bash
  journalctl --user -u jota -p err --no-pager
  ```

---

## Bateria de Pruebas

El proyecto cuenta con una cobertura integral de pruebas unitarias y de integracion:

```bash
source .venv/bin/activate
pytest tests/ -v
```

Comprobar estilo y formato de codigo:

```bash
ruff check .
```

---

## Solucion de Problemas

### Error de permisos al leer eventos de teclado (`/dev/input/*`)
Asegurate de que tu usuario pertenece al grupo `input`:
```bash
sudo usermod -aG input $USER
# Cierra sesion y vuelve a iniciar sesion para aplicar el grupo
```

### Transcripciones continuas sin hablar (ruido ambiental)
El modo manos libres continuo se encuentra desactivado por defecto (`HANDSFREE_ENABLED = False`). Jota solo captura audio mientras mantienes pulsada la tecla Copilot. Si activas manos libres con `JOTA_HANDSFREE=true`, incrementa el umbral de sensibilidad VAD:
```bash
export JOTA_VAD_THRESHOLD=0.035
```

### Las aplicaciones abiertas se cierran al detener Jota
Todas las aplicaciones lanzadas por Jota (`open_app`, `scrcpy`, `catt`) se ejecutan como procesos independientes desacoplados (`start_new_session=True`). Cerrar o reiniciar el servicio de Jota no interrumpe tus programas abiertos.

### Error al conectar por ADB al movil
Si el movil esta conectado por cable USB, comprueba que aparece como autorizado:
```bash
adb devices
```
Si aparece como `unauthorized`, acepta el dialogo de autorizacion en la pantalla del telefono. En dispositivos Xiaomi/HyperOS, habilita tambien **"Instalar via USB"** y **"Depuracion USB (ajustes de seguridad)"** en Opciones de desarrollador.
