# Jota Hub (Servidor Homelab / Docker - HUB-0.1)

Despliegue contenerizado y aislado del cerebro central de Jota para servidores homelab (ej. HP EliteDesk u otros servidores dedicados).
Permite que los satelites de escritorio, satelites de solo lectura y dispositivos moviles Android (JotaLink) interactuen con el asistente las 24 horas del dia de forma coordinada y segura.

---

## Caracteristicas Principales

- **Aislamiento Total**: Ejecucion en contenedor Docker (`compose.yaml`) con dependencias empaquetadas (Python 3.12, ffmpeg, CTranslate2, llama-cpp-python).
- **Persistencia Segura en SQLite**:
  - Almacenamiento local en `./data/jota.db` con permisos de fichero `0600` y modo WAL activado.
  - Cero puertos de base de datos expuestos a la red.
  - Cifrado en reposo para secretos y tokens mediante AES-256-GCM.
- **Coordinacion y Telemetria del Cluster**:
  - Auto-registro de satelites mediante huella criptografica inmutable (`node_id`).
  - Monitorizacion de latidos (heartbeats) y consolidacion de metricas de CPU, memoria, disco y contenedores Docker/Podman de todos los nodos.
- **Descarga Inteligente de Carga a GPU**:
  - Deteccion automatica de nodos de trabajo secundarios con GPU (ej. workstation con NVIDIA RTX 5070).
  - Delegacion de inferencias de alta resolucion a la GPU secundaria, con fallback transparente al LLM local del Hub ante apagado o desconexion.
- **STT y LLM Local Integrado**:
  - `faster-whisper` (int8 en CPU, optimizado con AVX2).
  - `Qwen 2.5 1.5B Instruct` (GGUF cuantizado q4_k_m, context 4096 tokens).
- **Multi-Red y Failover Seguro**:
  - Tailscale IP: `http://<ip-tailscale>:8765`
  - LAN Local IP: `http://<ip-lan>:8765`
- **Integraciones Homelab**: Music Assistant, Navidrome, Home Assistant y Docker API (`/var/run/docker.sock`).

---

## Puesta en Marcha

```bash
cd docker/jota-hub
docker compose up -d
```

---

## Verificacion

```bash
# Comprobar salud del servicio Hub
curl -s http://localhost:8765/health | jq .

# Comprobar estado consolidado del cluster homelab
curl -s -H "X-Jota-Token: tu_token_secreto" http://localhost:8765/api/v1/homelab/cluster_status | jq .

# Ver logs en tiempo real
docker compose logs -f
```
