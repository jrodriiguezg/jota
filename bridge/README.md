# Jota Bridge (JotaLink)

Modulo de integracion y puente remoto bidireccional entre el asistente de voz **Jota** (Fedora / Hyprland) y dispositivos **Android** mediante la red privada **Tailscale**.

---

## Caracteristicas Principales

### 1. Desde Android hacia el PC:
- **Invocacion de voz completa (Push-to-Talk):** Habla desde el telefono para ejecutar acciones en el PC o consultar a Jota; la respuesta hablada de Piper se reproduce en el telefono.
- **Consultas del PC:** Consulta de carga de CPU, uso de RAM, disco, ventana activa en Hyprland y tiempo encendido.
- **Captura de pantalla en tiempo real:** Visualiza la composicion actual del escritorio de Wayland (`grim`).
- **Sincronizacion bidireccional de portapapeles:** Envia o lee el portapapeles de Wayland (`wl-copy` / `wl-paste`).
- **Descarga remota de archivos:** Descarga archivos del PC al almacenamiento del telefono con lista blanca y bloqueo de rutas sensibles (`.ssh`, credenciales, `/etc`).

### 2. Desde el PC hacia Android (Jota por voz):
- *"Jota, encuentra mi movil"* o *"haz sonar mi telefono"* -> Dispara alarma acustica al maximo volumen en canal `STREAM_ALARM` y vibracion.
- *"Jota, ¿cuanta bateria le queda al movil?"* -> Consulta el porcentaje de bateria y estado de carga reportado por el dispositivo.
- *"Jota, copia esto a mi movil"* -> Coloca el texto en el portapapeles de Android.
- *"Jota, abre este enlace en mi telefono"* -> Abre la URL en el navegador de Android.

---

## Puesta en Marcha

### 1. Iniciar el servidor Bridge en el PC

Puedes iniciarlo directamente mediante el comando de consola registrado:

```bash
source .venv/bin/activate
jota-bridge
```

O ejecutando el modulo con Python:

```bash
source .venv/bin/activate
python -m bridge.server
```

Salida esperada:
```
==================================================
  Jota Bridge activo en http://0.0.0.0:8765
  Canal de vinculacion Android listo en /ws/phone
==================================================
```

### 2. Variables de Entorno Opcionales

| Variable | Valor por defecto | Descripcion |
|---|---|---|
| `JOTA_BRIDGE_HOST` | `0.0.0.0` | IP de escucha (accesible por la interfaz de Tailscale) |
| `JOTA_BRIDGE_PORT` | `8765` | Puerto de escucha HTTP y WebSocket |
| `JOTA_BRIDGE_API_KEY` | `jota-secret-tailscale-key` | Token de autenticacion compartido con la app Android |
| `JOTA_BRIDGE_TEMP_DIR` | `/tmp/jota_bridge` | Directorio para audios de entrada y respuesta TTS |

---

## Pruebas y Simulacion con CLI

El repositorio incluye un cliente de prueba en `bridge/test_client.py`:

```bash
# 1. Simular un telefono Android conectado (recibe alarmas, portapapeles y reporta bateria)
python bridge/test_client.py simulate-phone --battery 85

# 2. Consultar el estado del PC
python bridge/test_client.py status

# 3. Hacer una pregunta de texto a Jota en el PC
python bridge/test_client.py ask "¿Cual es la ventana activa?"

# 4. Obtener una captura de pantalla del PC
python bridge/test_client.py screenshot --out captura_pc.png

# 5. Descargar un archivo del PC
python bridge/test_client.py file README.md --out readme_descargado.md
```

---

## Aplicacion Android

El codigo fuente y la documentacion de la aplicacion nativa para Android se encuentran en:
- [`bridge/android/README.md`](file:///home/jrodriiguezg/Documentos/Proyectos/hyper/jota/bridge/android/README.md)
- [`bridge/android/app/`](file:///home/jrodriiguezg/Documentos/Proyectos/hyper/jota/bridge/android/app/)
