# Jota Bridge (BRIDGE-0.1) - Pasarela Movil y Aplicacion JotaLink

Jota Bridge es el componente opcional de integracion movil del ecosistema Jota. Proporciona la pasarela de comunicacion segura para conectar dispositivos Android (a traves de la aplicacion nativa JotaLink) con el servidor central (Jota Hub) o satelites de escritorio.

---

## 1. Caracteristicas de la Integracion Movil

- **Totalmente Opcional**: El ecosistema Jota (Hub y Satelites) funciona de forma 100% autonoma sin necesidad de instalar este componente ni la aplicacion movil.
- **Asistente Movil de Bolsillo**: Permite interactuar con Jota desde el smartphone mediante texto o mensajes de voz, recibiendo respuestas procesadas por el Hub 24/7.
- **Portapapeles Universal**: Sincronizacion bidireccional instantanea de texto y enlaces entre el portapapeles de Android y las sesiones activas de escritorio Linux (Wayland / Hyprland).
- **Control Remoto Multimedia**: Control de reproduccion para Navidrome y Music Assistant desde la pantalla del telefono.
- **Supervision del Homelab y Satelites**: Cuadro de mando movil para consultar el estado de contenedores Docker/Podman y el estado en tiempo real de todos los satelites conectados.
- **Disparador de Escenas Remotas**: Ejecucion de rutinas automatizadas predefinidas (ej. encender pantallas, preparar entorno de trabajo, apagar musica) sobre satelites autorizados.

---

## 2. Topologia de Conexion y Red

La comunicacion movil con el ecosistema se realiza exclusivamente sobre redes privadas y cifradas:

```
[ App Android JotaLink ]
          │
          │ (HTTP REST / WebSockets con X-Jota-Token)
          ▼
   ┌──────────────┐
   │ Red Privada  │  --> Red Local WiFi (LAN 192.168.x.x)
   │  o Tailscale │  --> Malla Cifrada WireGuard (Tailscale 100.x.x.x)
   └──────────────┘
          │
          ▼
[ Jota Hub (:8765) ] ───> Coordina Satelites y Homelab
```

- **Politica de Seguridad**: JotaLink nunca expone puertos en internet publico sin cifrado. Se conecta mediante la IP local de tu router o mediante la IP asignada por Tailscale a tu servidor.
- **Autenticacion**: Todas las peticiones HTTP y suscripciones WebSocket validan la cabecera `X-Jota-Token: <token_secreto>`.

---

## 3. Especificacion de la API Movil (Bridge Endpoints)

| Metodo | Endpoint | Descripcion | Autenticacion |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/mobile/status` | Comprobacion de enlace y estado del cluster | `X-Jota-Token` |
| `POST` | `/api/v1/assistant/query` | Envio de consulta textual o de audio al LLM | `X-Jota-Token` |
| `GET` | `/api/v1/clipboard` | Obtener contenido actual del portapapeles del cluster | `X-Jota-Token` |
| `POST` | `/api/v1/clipboard` | Enviar texto desde el movil al portapapeles del escritorio | `X-Jota-Token` |
| `GET` | `/api/v1/homelab/containers` | Lista de contenedores y salud de los servidores | `X-Jota-Token` |
| `GET` | `/api/v1/nodes/list` | Lista de satelites registrados y estado en vivo | `X-Jota-Token` |
| `POST` | `/api/v1/scenes/execute` | Disparar una escena sobre uno o mas satelites | `X-Jota-Token` |
| `WS` | `/ws/mobile` | Canal bidireccional para eventos push y portapapeles | `X-Jota-Token` |

---

## 4. Instalacion y Puesta en Marcha de la App Android (JotaLink)

### Descarga del Instalador APK

1. **Desde tu propio Jota Hub**: Si tienes el Hub desplegado, descarga directamente el archivo APK compilado accediendo desde el navegador de tu movil a:
   ```
   http://<IP_HUB_O_TAILSCALE>:8765/download/jotalink.apk
   ```
2. **Desde los releases del repositorio**: Descarga la ultima version `JotaLink-release.apk` desde la pestana de Releases de GitHub.

### Instalacion en Android

1. Abre el archivo `.apk` descargado en tu dispositivo Android.
2. Si el sistema lo solicita, autoriza la instalacion de aplicaciones desde fuentes desconocidas para tu navegador o gestor de archivos.
3. Pulsa sobre **Instalar** y abre la aplicacion **JotaLink**.

### Permisos Requeridos y Justificacion

- **Acceso a la Red (INTERNET)**: Para comunicarse con el Hub mediante HTTP y WebSocket sobre LAN o Tailscale.
- **Grabacion de Audio (RECORD_AUDIO)**: Opcional, requerido unicamente si deseas enviar comandos de voz directamente desde la app.
- **Servicio en Primer Plano (FOREGROUND_SERVICE)**: Mantiene la escucha de sincronizacion del portapapeles en segundo plano de manera persistente.

---

## 5. Vinculacion de la App con el Hub

Al abrir JotaLink por primera vez, encontraras la pantalla de configuracion inicial:

1. **Direccion del Servidor (Server URL)**:
   - En casa: `http://192.168.1.100:8765` (sustituye por la IP de tu servidor).
   - Fuera de casa con Tailscale activo: `http://100.x.x.x:8765` (sustituye por la IP Tailscale de tu Hub).
2. **Token de Acceso (API Token)**:
   - Introduce exactamente el mismo valor configurado en la variable `JOTA_BRIDGE_KEY` del archivo `.env` del Hub.
3. Pulsa **Probar Conexion**.
   - La aplicacion verificara la conexion con `/health` y `/api/v1/mobile/status`.
   - Si las credenciales son correctas, el indicador de estado cambiara a verde y podras comenzar a utilizar todas las funciones.

---

## 6. Ejecucion del Bridge como Demonio Local en PC (Modo Standalone Opcional)

Si utilizas Jota en modo Standalone (sin Hub dedicado) pero deseas sincronizar tu movil con tu estacion de trabajo cuando esta encendida:

```bash
# Iniciar el servicio local del bridge
python3 -m bridge.server --port 8765 --token mi_token_secreto
```

O activando el servicio de systemd correspondiente:

```bash
systemctl --user enable --now jota-bridge.service
```

---

## 7. Pruebas y Diagnostico

Para verificar que el servicio Bridge y sus endpoints responden adecuadamente:

```bash
# Ejecutar verificacion de estado local
python3 -m bridge.cli status

# Ejecutar bateria de pruebas de integracion
pytest tests/test_bridge_api.py -q
```
