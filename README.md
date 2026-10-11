# Jota - Asistente de Voz Local y Ecosistema Multi-Dispositivo

Jota es un asistente de voz autonomo, inteligente y privado para Linux (optimizado para entornos Wayland / Hyprland) con capacidad de extension multi-dispositivo y homelab.

Permite controlar el sistema operativo mediante lenguaje natural, gestionar ventanas, automatizar rutinas mediante escenas YAML, sincronizar dispositivos Android (portapapeles universal, capturas, reproduccion), controlar servidores de musica (Music Assistant, Navidrome) y supervisar contenedores del homelab.

---

## Indice

- [Pregunta Frecuente: Es obligatorio un servidor?](#pregunta-frecuente-es-obligatorio-un-servidor)
- [Las Tres Versiones y Ramas del Proyecto](#las-tres-versiones-y-ramas-del-proyecto)
  - [Modo 1: Solo PC (Standalone - Rama main)](#modo-1-solo-pc-standalone---rama-main)
  - [Modo 2: PC + Movil (Bridge - Rama bridge)](#modo-2-pc--movil-bridge---rama-bridge)
  - [Modo 3: Servidor Homelab 24/7 (Hub Docker - Rama jota-hub)](#modo-3-servidor-homelab-247-hub-docker---rama-jota-hub)
- [Tabla Comparativa de Modos](#tabla-comparativa-de-modos)
- [Instalador Automatizado Unificado](#instalador-automatizado-unificado)
- [Arquitectura Tecnica](#arquitectura-tecnica)
- [Configuracion de cada Modo](#configuracion-de-cada-modo)
  - [Configuracion del PC (jota/config.py)](#configuracion-del-pc-jotaconfigpy)
  - [Configuracion del Bridge (bridge/config.py)](#configuracion-del-bridge-bridgeconfigpy)
  - [Configuracion de Jota Hub (compose.yaml)](#configuracion-de-jota-hub-composeyaml)
  - [Descarga e Instalacion de la App Android JotaLink](#descarga-e-instalacion-de-la-app-android-jotalink)
  - [Configuracion de la App Android JotaLink](#configuracion-de-la-app-android-jotalink)
- [Ejecucion como Servicio Systemd](#ejecucion-como-servicio-systemd)
- [Consultar Registros con Journalctl](#consultar-registros-con-journalctl)
- [Bateria de Pruebas](#bateria-de-pruebas)
- [Solucion de Problemas](#solucion-de-problemas)

---

## Pregunta Frecuente: Es obligatorio un servidor?

**NO, el servidor NO es obligatorio.**

Jota fue disenado desde su concepcion como un asistente **100% local, offline y autonomo** para tu ordenador de escritorio. No requiere ningun servidor externo, cuenta en la nube ni conexion a internet para funcionar.

El ecosistema cuenta con tres modos independientes para adaptarse a tus necesidades y hardware:

1. **Puedes usar Jota unicamente en tu PC** (Modo Standalone): reconocimiento de voz local, LLM local y control del escritorio sin tocar la red.
2. **Puedes usar Jota entre tu PC y tu movil Android** (Modo Bridge): tu propio PC actua como servidor cuando esta encendido. Tampoco requiere servidores externos.
3. **Puedes usar Jota en un servidor Homelab 24/7** (Modo Hub): unicamente si dispones de un servidor (ej. HP EliteDesk) y deseas que el asistente este despierto las 24 horas del dia para hablarle desde el movil con el PC apagado o controlar la musica de toda la casa.

---

## Las Tres Versiones y Ramas del Proyecto

El repositorio esta organizado en tres ramas principales, cada una optimizada para un caso de uso especifico:

```
                      ┌────────────────────────────────────────┐
                      │            JOTA ECOSISTEMA             │
                      └────────────────────────────────────────┘
                                           │
         ┌─────────────────────────────────┼─────────────────────────────────┐
         │                                 │                                 │
         ▼                                 ▼                                 ▼
   [ Rama main ]                    [ Rama bridge ]                  [ Rama jota-hub ]
 Modo 1: Solo PC                   Modo 2: PC + Movil               Modo 3: Homelab 24/7
 • 100% offline local              • PC = Servidor puente           • Docker en servidor homelab
 • 0 dependencias de red           • Vinculacion Android JotaLink   • Movil activo sin encender PC
 • Tecla Copilot (evdev)           • Portapapeles bidireccional     • faster-whisper + Qwen 1.5B/0.5B
 • whisper.cpp + Qwen local        • Capturas y control multimedia  • Music Assistant + Navidrome
 • Orbe visual flotante Wayland    • Apagas PC = Movil desconecta   • Wake-on-LAN para encender PC
```

---

### Modo 1: Solo PC (Standalone - Rama main)

Este es el modo base original de Jota. Esta pensado para usuarios que solo quieren un asistente de escritorio inteligente en su equipo con Linux.

- **Como funciona:**
  - Pulsas la tecla **Copilot** (o la tecla configurada) en tu teclado físico.
  - Mantienes pulsada la tecla mientras hablas; al soltarla, el motor local **whisper.cpp** transcribe tu voz.
  - El modelo local **Qwen2.5-1.5B** (o 0.6B) deduce la intencion y ejecuta la orden sobre tu entorno Hyprland/Wayland (ajustar volumen con WirePlumber, lanzar aplicaciones, fijar temporizadores, consultar notas, hora o clima).
  - El motor local **piper-tts** sintetiza la respuesta y la emite por los altavoces de tu ordenador.
  - Un **orbe flotante** translucido en Wayland proporciona feedback visual instantaneo (escuchando, pensando, hablando).
- **Ventajas:**
  - 100% privado y seguro (cero telemetria, cero peticiones salientes a internet).
  - Tiempos de respuesta ultra-rapidos (<1 segundo).
  - No consume recursos en ningun otro equipo de la red.
- **Instalacion:**
  ```bash
  git checkout main
  bash install.sh --mode=standalone
  ```

---

### Modo 2: PC + Movil (Bridge - Rama bridge)

Este modo anade un servidor puente de comunicacion local en tu PC para enlazar tu smartphone Android mediante la aplicacion nativa **JotaLink**.

- **Como funciona:**
  - Tu propio PC ejecuta el servicio `jota-bridge` en segundo plano, abriendo un puerto local (`8765`).
  - La app Android JotaLink se conecta a tu PC mediante **cable USB** (ADB reverse, cero latencia), **red Wi-Fi local** o a traves de **Tailscale**.
  - **Portapapeles universal bidireccional:** Copias un texto o enlace en el movil y se copia de inmediato en el portapapeles de tu PC; copias en el PC y aparece en el movil.
  - **Capturas de pantalla en remoto:** Visualiza y guarda en la galeria de tu movil capturas de las pantallas de tu PC en tiempo real.
  - **Control Multimedia MPRIS:** Pausa, reanuda o cambia de cancion en el PC desde las notificaciones o la interfaz del movil.
  - **Microfono remoto:** Puedes pulsar el boton de voz en la app del movil para hablarle a Jota y que ejecute ordenes en tu PC.
- **Limitacion:**
  - Dado que tu PC es el host del servicio, si apagas el PC o lo pones en suspension, la aplicacion movil perdera la conexion.
- **Instalacion:**
  ```bash
  git checkout bridge
  bash install.sh --mode=bridge
  ```

---

### Modo 3: Servidor Homelab 24/7 (Hub Docker - Rama jota-hub)

Este modo traslada el cerebro central de Jota a un contenedor Docker aislado dentro de tu servidor homelab (ej. HP EliteDesk, Intel NUC, Raspberry Pi o NAS).

- **Como funciona:**
  - El contenedor `jota-hub` corre las 24 horas del dia en el servidor.
  - Cuenta con un motor de transcripcion optimizado para CPU multinucleo (**faster-whisper** con cuantizacion `int8`) y el modelo **Qwen2.5-1.5B** (o `0.5B` para maxima ligereza).
  - Tu telefono Android (JotaLink) se conecta directamente al servidor Hub (por Tailscale `100.x.y.z:8765` con fallback automatico a LAN `192.168.1.100:8765`).
  - **Independencia del PC:** Puedes hablarle a Jota desde la cama, la cocina o fuera de casa sin necesidad de que tu PC de escritorio este encendido.
  - **Control del Homelab:** Puedes consultar el estado de los contenedores Docker, controlar la reproduccion multiroom en **Music Assistant**, buscar pistas en **Navidrome** o consultar **Home Assistant**.
  - **Encendido remoto del PC:** Si necesitas tu ordenador, solo tienes que decirle a Jota desde el movil: *"Despierta el PC"*; Jota Hub emitira un paquete magico Wake-on-LAN hacia la tarjeta de red de tu PC para encenderlo inmediatamente.
- **Instalacion en el Servidor:**
  ```bash
  git checkout jota-hub
  bash install.sh --mode=hub
  ```

---

## Tabla Comparativa de Modos

| Caracteristica | Modo 1: Standalone (`main`) | Modo 2: Bridge (`bridge`) | Modo 3: Hub Homelab (`jota-hub`) |
|---|---|---|---|
| **Dispositivos soportados** | Solo PC | PC + Smartphone Android | PC + Smartphone Android + Homelab |
| **Requiere servidor externo?** | No | No (el PC es el host) | Si (contenedor Docker en servidor) |
| **Funciona con el PC apagado?** | No | No | Si (24/7 desde el movil) |
| **Motor STT (Voz a texto)** | `whisper.cpp` nativo | `whisper.cpp` nativo | `faster-whisper` (CTranslate2 int8) |
| **Motor LLM (Inferencia)** | Qwen 2.5 1.5B / 0.6B | Qwen 2.5 1.5B / 0.6B | Qwen 2.5 1.5B / 0.5B (GGUF) |
| **Sintesis TTS (Texto a voz)** | `piper-tts` por altavoces PC | `piper-tts` (PC y streaming movil) | `piper-tts` / streaming de audio |
| **Portapapeles Universal** | No aplicable | Si (Bidireccional PC <-> Movil) | Sincronizable via Bridge |
| **Capturas remotas de pantalla** | No aplicable | Si (Galeria Android en directo) | Via cliente PC conectado |
| **Transferencia Music Assistant** | Local | Si (PC <-> Movil) | Si (Servidor central 24/7) |
| **Encendido por Wake-on-LAN** | No aplicable | No aplicable | Si (Despierta el PC desde el movil) |
| **Consumo de recursos** | Puntual (solo al pulsar tecla) | Bajo en reposo (~30MB) | Constante acotado (~1.2GB RAM en server) |

---

## Instalador Automatizado Unificado

El repositorio incluye el script [`install.sh`](file:///home/jrodriiguezg/Documentos/Proyectos/hyper/jota/install.sh), que automatiza la resolucion de paquetes del sistema, grupos de usuario, compilacion de binarios, descarga de modelos cuantizados y configuracion de servicios systemd o contenedores Docker.

### 1. Ejecucion interactiva con menu guiado
```bash
bash install.sh
```

El script te preguntara que modo deseas instalar:
```
Selecciona el modo de instalacion:
  1) Solo PC (Standalone)   - 100% offline en tu PC, sin red ni servidor.
  2) PC + Movil (Bridge)    - Tu PC actua de puente para la app Android.
  3) Servidor Homelab (Hub) - Contenedor Docker 24/7 en servidor homelab.

Opcion [1-3]:
```

### 2. Ejecucion desatendida por flags

- **Instalar Modo 1 (Solo PC):**
  ```bash
  bash install.sh --mode=standalone
  ```

- **Instalar Modo 2 (PC + Movil):**
  ```bash
  bash install.sh --mode=bridge
  ```

- **Instalar Modo 3 (Servidor Homelab / Docker Hub):**
  ```bash
  bash install.sh --mode=hub
  ```

---

## Arquitectura Tecnica

```
 +---------------------------------------------------------------------------------+
 |                              DISPOSITIVO DE ENTRADA                             |
 |   Tecla Copilot (PC / evdev)    o    Boton de Voz en Android (JotaLink / WS)    |
 +---------------------------------------------------------------------------------+
                                          |
                                          v
 +---------------------------------------------------------------------------------+
 |                           RECONOCIMIENTO DE VOZ (STT)                           |
 |          whisper.cpp (ggml-small.bin)   o   faster-whisper (CPU int8)           |
 +---------------------------------------------------------------------------------+
                                          |
                                          v
 +---------------------------------------------------------------------------------+
 |                          ENRUTADOR HIBRIDO DE INTENCIONES                       |
 |    1. Fast Intents Regex (<1ms, 0% CPU): Volumen, Media, Tiempo, Temporizadores |
 |    2. LLM Tool Calling (Qwen2.5-1.5B Instruct en llama-cpp-python)              |
 +---------------------------------------------------------------------------------+
                                          |
                                          v
 +---------------------------------------------------------------------------------+
 |                            EJECUCION DE HERRAMIENTAS                            |
 |  Escritorio: hyprctl, wpctl, playerctl, grim, scrcpy, dolphin, wl-copy          |
 |  Homelab: Music Assistant API, Navidrome API, Docker Socket, Wake-on-LAN        |
 +---------------------------------------------------------------------------------+
                                          |
                                          v
 +---------------------------------------------------------------------------------+
 |                           RESPUESTA HABLADA (TTS) Y UI                          |
 |  Audio: piper-tts (es_ES-sharvard-medium) -> Altavoces PC o Streaming a Movil   |
 |  Visual: Orbe Wayland flotante (GTK Layer Shell) o Notificacion en JotaLink     |
 +---------------------------------------------------------------------------------+
```

---

## Configuracion de cada Modo

### Configuracion del PC (`jota/config.py`)

Puedes personalizar el comportamiento en tu PC editando [`jota/config.py`](file:///home/jrodriiguezg/Documentos/Proyectos/hyper/jota/jota/config.py) o mediante variables de entorno:

| Variable | Valor por defecto | Descripcion |
|---|---|---|
| `JOTA_LLM_PROFILE` | `lightweight` | Perfil de modelo (`lightweight` para 1.5B/0.5B, `quality` para 3B/7B). |
| `JOTA_LLM_CTX` | `4096` | Tamano de ventana de contexto en tokens. |
| `JOTA_LLM_THREADS` | `4` | Hilos de CPU asignados a la inferencia (evita saturar la CPU). |
| `JOTA_STT_ENGINE` | `auto` | Motor STT (`auto`, `whisper_cli` o `faster_whisper`). |
| `JOTA_ORB_ENABLED` | `true` | Habilitar orbe flotante en Wayland. |
| `JOTA_ORB_AUTO_HIDE` | `true` | Ocultar automaticamente el orbe cuando este en reposo. |
| `JOTA_HANDSFREE` | `false` | Escucha manos libres continua con VAD (desactivada por defecto). |

### Configuracion del Bridge (`bridge/config.py`)

Ajustes para la exposicion de la API y canal WebSocket en [`bridge/config.py`](file:///home/jrodriiguezg/Documentos/Proyectos/hyper/jota/bridge/config.py):

| Variable | Valor por defecto | Descripcion |
|---|---|---|
| `JOTA_BRIDGE_HOST` | `0.0.0.0` | Direccion de escucha (accesible por LAN y Tailscale). |
| `JOTA_BRIDGE_PORT` | `8765` | Puerto TCP de comunicacion. |
| `JOTA_BRIDGE_API_KEY` | `jota-secret-tailscale-key` | Token de autenticacion para clientes remotos. |
| `JOTA_BRIDGE_MDNS` | `true` | Anuncio automatico mDNS / ZeroConf en la red local. |
| `JOTA_BRIDGE_AUTO_ADB` | `true` | Configuracion automatica de `adb reverse` al conectar cable USB. |

### Configuracion de Jota Hub (`compose.yaml`)

El archivo [`docker/jota-hub/compose.yaml`](file:///home/jrodriiguezg/Documentos/Proyectos/hyper/jota/docker/jota-hub/compose.yaml) define el despliegue contenerizado:

```yaml
services:
  jota-hub:
    build:
      context: .
      dockerfile: Dockerfile
    image: jota-hub:latest
    container_name: jota-hub
    restart: unless-stopped
    ports:
      - "8765:8765"
    environment:
      - JOTA_BRIDGE_HOST=0.0.0.0
      - JOTA_BRIDGE_PORT=8765
      - JOTA_BRIDGE_API_KEY=jota-secret-tailscale-key
      - JOTA_STT_ENGINE=faster_whisper
      - JOTA_FASTER_WHISPER_MODEL=base
      - JOTA_FASTER_WHISPER_COMPUTE=int8
      - JOTA_LLM_MODEL=/app/models/qwen/qwen2.5-1.5b-instruct-q4_k_m.gguf
      - JOTA_LLM_CTX=4096
      - JOTA_LLM_THREADS=4
      - JOTA_ORB_ENABLED=false
      - JOTA_TRAY=false
      - MUSIC_ASSISTANT_URL=http://100.x.y.z:8095
      - MUSIC_ASSISTANT_TOKEN=tu_token_larga_duracion
      - NAVIDROME_URL=https://navidrome.tudominio.link
    volumes:
      - ./data:/app/data
      - ./models:/app/models:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
```

### Descarga e Instalacion de la App Android JotaLink

Los archivos binarios compilados (`.apk`) no se guardan directamente dentro del historial de Git para evitar sobrecargar el repositorio con archivos binarios pesados. Dispones de varias opciones para obtener e instalar la aplicacion en tu telefono:

#### Opcion A: Descarga desde GitHub (Releases y Actions)
1. **GitHub Releases:** Dirigete a la seccion [Releases de GitHub](https://github.com/jrodriiguezg/jota/releases) y descarga el archivo `app-debug.apk` o `JotaLink.apk` adjunto a la ultima version publicada.
2. **GitHub Actions (Artifacts):** Cada cambio enviado a las ramas `main`, `bridge` o `jota-hub` ejecuta un flujo automatizado (`.github/workflows/android.yml`) que compila la aplicacion y genera un artefacto descargable denominado `JotaLink-APK`.

#### Opcion B: Descarga directa desde tu propio Jota Hub o PC Bridge
Tanto el contenedor Docker de **Jota Hub** como el servicio **Jota Bridge** ofrecen un endpoint HTTP directo para descargar el instalador APK sin salir de tu red:
- **Desde Tailscale (remoto):** `http://100.x.y.z:8765/download/jotalink.apk`
- **Desde LAN (local):** `http://192.168.1.100:8765/download/jotalink.apk` (o la IP local de tu PC en modo Bridge)

Abre esa direccion en el navegador de tu movil (Chrome, Firefox, etc.) para descargar el archivo e instalarlo directamente pulsando sobre la notificacion de descarga.

#### Opcion C: Instalacion directa por cable USB (ADB)
Si tienes el telefono conectado al ordenador por USB y con la depuracion USB activada:
```bash
adb install -r bridge/android/app/build/outputs/apk/debug/app-debug.apk
```

#### Opcion D: Compilacion manual desde codigo fuente
Si deseas compilar la aplicacion por tu cuenta en tu maquina:
```bash
cd bridge/android
./gradlew assembleDebug
```
El archivo binario generado estara ubicado en `bridge/android/app/build/outputs/apk/debug/app-debug.apk`.

### Configuracion de la App Android JotaLink

La aplicacion Android (`bridge/android`) incluye soporte para conmutacion por error (**Failover automatico**):

1. **Abre JotaLink** en tu dispositivo.
2. Despliega el panel de **Conexion y Red**.
3. Configura las dos URLs disponibles:
   - **Server URL Principal (Tailscale / Remoto):** `http://100.x.y.z:8765`
   - **Fallback Server URL (LAN / Alternativo):** `http://192.168.1.100:8765`
4. Pulsa **Guardar y Conectar**.

Si sales de casa o la red local cambia, la aplicacion intentara comunicarse con la IP primaria y, ante cualquier fallo de red o tiempo de espera, conmutara de forma transparente a la IP de fallback sin interrumpir tus solicitudes.

---

## Ejecucion como Servicio Systemd

Para que Jota arranque automaticamente al iniciar tu equipo de escritorio y sobreviva a cierres de terminal:

### 1. Archivo de unidad de usuario (`~/.config/systemd/user/jota.service`)

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
PassEnvironment=WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP XDG_RUNTIME_DIR

StandardOutput=journal
StandardError=journal
SyslogIdentifier=jota

[Install]
WantedBy=default.target
```

### 2. Habilitar persistencia de usuario y activar servicio
```bash
# Permitir que los servicios de usuario arranquen al encender el PC
loginctl enable-linger $USER

# Recargar daemon y activar
systemctl --user daemon-reload
systemctl --user enable --now jota.service
```

---

## Consultar Registros con Journalctl

```bash
# Seguir registros en tiempo real
journalctl --user -u jota -f

# Ver ultimas 50 lineas estructuradas
journalctl --user -u jota -n 50 --no-pager

# Filtrar unicamente errores
journalctl --user -u jota -p err --no-pager
```

---

## Bateria de Pruebas

Para validar el funcionamiento del conjunto de herramientas y el enrutador:

```bash
source .venv/bin/activate
pytest tests/ -v
ruff check .
```

---

## Solucion de Problemas

### 1. Error de permisos en teclado (`/dev/input/*`)
Si la tecla Copilot no responde, agrega tu usuario al grupo `input`:
```bash
sudo usermod -aG input $USER
# Cierra sesion y vuelve a iniciarla para aplicar el cambio
```

### 2. El orbe visual no inicia en Wayland
Asegurate de que la sesion grafica exporta `WAYLAND_DISPLAY` hacia systemd:
```bash
systemctl --user import-environment WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP
```
El cliente de Jota detecta automaticamente los sockets activos en `/run/user/$UID/wayland-*`.

### 3. Jota Hub en Docker no puede conectarse a Music Assistant o Navidrome
Verifica que las variables de entorno de red apunten a la IP accesible desde el contenedor (por ejemplo, la IP de Tailscale del host `100.x.y.z` o la IP de red local `192.168.1.100`).
