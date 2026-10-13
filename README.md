# Jota Hub (HUB-0.1) - Servidor Central y Orquestador de Computo

Jota Hub es el cerebro centralizado y orquestador permanente (24/7) del ecosistema Jota. Se ejecuta en un servidor homelab o maquina dedicada mediante contenedores Docker, coordinando satelites de escritorio, satelites de monitorizacion y clientes moviles.

---

## 1. Caracteristicas Principales

- **Nodo Central 24/7**: Permite que el asistente responda consultas, coordine la musica de la casa y supervise la infraestructura sin depender de que tu PC de escritorio este encendido.
- **Despliegue Oficial en Contenedor**: Empaquetado aislado y reproducible con Docker y Docker Compose (`compose.yaml`).
- **Arquitectura Maestro / Secundario**:
  - **Hub Maestro (24/7)**: Nodo siempre activo (en homelab o servidor de bajo consumo). Gestiona el estado, la memoria conversacional y despacha inferencias base con Qwen 2.5 1.5B.
  - **Hub Secundario / Worker de Computo (Opcional)**: Cuando tu estacion de trabajo con GPU (ej. NVIDIA RTX 5070) esta encendida, se anuncia mediante heartbeat al Maestro. El Maestro le delega solicitudes pesadas (modelos 7B/14B, vision o transcripcion por lotes). Si la estacion de trabajo se apaga, el Maestro asume la carga automaticamente sin interrupciones.
- **Seguridad y Base de Datos SQLite**:
  - **Sin exposicion de red**: SQLite es un motor embebido en archivo local (`jota.db`). No abre puertos de red externos; nadie puede conectarse directamente a la base de datos por TCP/UDP.
  - **Permisos de sistema de ficheros**: Almacenado en volumen protegido con permisos estrictos `0600`.
  - **Cifrado en reposo**: Las credenciales, tokens y huellas de hardware se cifran a nivel de aplicacion con AES-256-GCM antes de guardarse en disco. Soporte opcional para cifrado completo de base de datos con SQLCipher.
- **Identificacion Infalsificable de Nodos**:
  - Cada satelite o nodo que se conecta es autenticado mediante su `node_id` criptografico generado a partir del hardware del host (`/etc/machine-id`, UUID de placa base DMI y direccion MAC) y un token de red (`X-Jota-Token`).
- **Telemetria Multi-Servidor**:
  - Recolecta el estado de contenedores Docker/Podman, metricas de CPU/RAM/Disco y servicios de todos los servidores registrados en el cluster.

---

## 2. Arquitectura de Red y Comunicacion

El Hub escucha exclusivamente en interfaces de red local privada (LAN) o en la malla cifrada de **Tailscale**:

```
[ Satelite Escritorio (PC) ] ──┐
[ Satelite Headless (Servidor B)] ┼──> [ Jota Hub (Maestro 24/7) ] <─── [ Hub Secundario (GPU) ]
[ Cliente Movil (JotaLink) ] ──┘         (:8765 con X-Jota-Token)           (Offload de computo)
```

- **Puerto oficial**: `8765` (HTTP REST + WebSockets).
- **Cabecera de autenticacion**: `X-Jota-Token: <tu_token_secreto>`.
- **Politica de red**: Se recomienda encarecidamente utilizar Tailscale (`100.x.x.x`) para acceso fuera de casa o red local privada (`192.168.x.x` / `10.x.x.x`). No exponer directamente a internet sin tunel seguro.

---

## 3. Puesta en Marcha Rapida

### Requisitos Previos

- Docker 24.0+ y Docker Compose v2.
- (Opcional) Drivers NVIDIA y `nvidia-container-toolkit` si se ejecuta en un host con aceleracion por GPU.

### Estructura de Despliegue

```bash
mkdir -p ~/jota-hub/data ~/jota-hub/models
cd ~/jota-hub
```

Copia los archivos desde `docker/jota-hub/`:
- `compose.yaml`
- `.env.example` (renombralo a `.env`)

### Configuracion de Entorno (`.env`)

```ini
# Clave API / Token secreto del cluster Jota
JOTA_BRIDGE_KEY=tu_token_secreto_muy_seguro_aqui

# Puerto de exposicion en el host
JOTA_HUB_PORT=8765

# Parametros del modelo LLM
JOTA_LLM_THREADS=4
JOTA_LLM_CONTEXT=4096

# Integraciones de musica en homelab (opcionales)
NAVIDROME_URL=http://192.168.1.100:4533
NAVIDROME_USER=mi_usuario
NAVIDROME_PASSWORD=mi_password
MUSIC_ASSISTANT_URL=http://192.168.1.100:8095
```

### Iniciar el Contenedor

```bash
# Iniciar en segundo plano
docker compose up -d

# Comprobar logs de inicializacion
docker compose logs -f
```

---

## 4. Endpoints Principales de la API

| Metodo | Endpoint | Descripcion | Autenticacion |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Estado del servicio y nodos conectados | No requerida |
| `POST` | `/api/v1/nodes/register` | Registro inicial de satelite con hardware fingerprint | `X-Jota-Token` |
| `POST` | `/api/v1/nodes/heartbeat` | Latido periodico de salud y recursos de satelites | `X-Jota-Token` |
| `POST` | `/api/v1/telemetry/report` | Envio de metricas y contenedores desde satelites | `X-Jota-Token` |
| `POST` | `/api/v1/assistant/query` | Procesamiento de intenciones y consultas del LLM | `X-Jota-Token` |
| `GET` | `/api/v1/homelab/containers`| Listado de contenedores de todos los servidores | `X-Jota-Token` |
| `GET` | `/download/jotalink.apk` | Descarga directa de la app Android JotaLink | Opcional |

---

## 5. Mantenimiento y Backups

- **Base de datos y estado**: Se conserva en el volumen local mapeado en `./data/jota.db`.
- **Copia de seguridad**:
  ```bash
  # Crear backup consistente con SQLite online
  docker compose exec jota-hub sqlite3 /app/data/jota.db ".backup '/app/data/jota_backup.db'"
  ```
- **Actualizacion del contenedor**:
  ```bash
  docker compose pull
  docker compose up -d --remove-orphans
  ```
