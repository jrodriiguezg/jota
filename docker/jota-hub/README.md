# Jota Hub (Servidor Homelab / Docker)

Despliegue contenerizado y aislado del cerebro central de Jota para servidores homelab (ej. HP EliteDesk).
Permite que los dispositivos moviles Android (JotaLink) y clientes ligeros interactuen con el asistente las 24 horas del dia sin necesidad de que el PC de escritorio este encendido.

## Caracteristicas

- **Aislamiento Total**: Corre en un contenedor Docker con dependencias empaquetadas (Python 3.12, ffmpeg, CTranslate2, llama-cpp-python).
- **STT de Alto Rendimiento**: `faster-whisper` (int8 en CPU, optimizado con AVX2).
- **LLM Local**: `Qwen 2.5 1.5B Instruct` (GGUF cuantizado q4_k_m, context 4096 tokens).
- **Multi-Red y Failover**:
  - Tailscale IP: `http://<ip-tailscale>:8765`
  - LAN Local IP: `http://<ip-lan>:8765`
- **Integraciones Homelab**: Music Assistant, Navidrome, Home Assistant y Docker API (`/var/run/docker.sock`).

## Puesta en Marcha

```bash
cd /home/user/docker/jota-hub
docker compose up -d
```

## Verificacion

```bash
# Comprobar estado del servicio local o remotamente
curl -s http://localhost:8765/api/v1/pc/status | jq .

# Ver logs en tiempo real
docker compose logs -f
```
