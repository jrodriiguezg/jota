# Jota Satelite (satelite-0.1) - Cliente de Escritorio y Nodo de Telemetria

Jota Satelite es el componente cliente del ecosistema Jota diseñado para ejecutarse de forma nativa en sistemas operativos Linux (estaciones de trabajo, portatiles o servidores homelab secundarios). Conecta cada maquina al servidor central (Jota Hub) a traves de una red local segura o Tailscale.

---

## 1. Perfiles de Ejecucion

Jota Satelite se adapta al rol de cada equipo mediante dos perfiles principales:

### Perfil 1: Desktop (Interactivo)
Pensado para la estacion de trabajo principal o portatiles con entorno de escritorio (especialmente optimizado para Wayland / Hyprland):
- **Disparador por hardware (evdev)**: Deteccion nativa de la tecla dedicada de Copilot u otros atajos a nivel de kernel, sin depender de intermediarios.
- **Captura y reproduccion de audio**: Integracion con PipeWire y WirePlumber para captura de microfono y reproduccion de respuestas por altavoces.
- **Transcripcion y sintesis de voz**: Motor STT local ultra-rapido (Whisper base/small) y sintesis TTS (Piper nativo es_ES).
- **Interfaz visual Wayland Orb**: Indicador flotante y minimalista con GTK 4 y Layer Shell (`jota-orb`) que muestra el estado del asistente (escuchando, pensando, hablando).
- **Control del entorno de escritorio**: Interaccion con Hyprland IPC, gestion de ventanas y lanzamiento de aplicaciones locales.

### Perfil 2: Headless (Servidores y Homelab de Solo Lectura)
Pensado para servidores secundarios, NAS o nodos auxiliares donde no hay microfono, altavoces ni entorno grafico:
- **Sin dependencias multimedia**: No requiere PipeWire, GTK, X11 ni Wayland.
- **Telemetria de contenedores**: Inspeccion del socket local de Docker o Podman para reportar estado y salud de los contenedores al Hub.
- **Metricas de sistema**: Recoleccion periodica de uso de CPU, memoria RAM, espacio en discos y temperaturas.
- **Monitorizacion de servicios systemd**: Comprobacion de unidades esenciales en segundo plano.
- **Seguridad de solo lectura**: En este perfil el nodo solo envia informacion y no ejecuta comandos arbitrarios del sistema, protegiendo la integridad del servidor.

---

## 2. Identificacion de Hardware Infalsificable (node_id)

Para garantizar que ningun nodo pueda ser suplantado o colisionar en el cluster, cada satelite genera una huella criptografica inmutable basada en el hardware fisico del host:

1. **Machine ID**: Identificador unico persistente de `/etc/machine-id` (o `/var/lib/dbus/machine-id`).
2. **Product UUID**: Identificador DMI unico de la placa base desde `/sys/class/dmi/id/product_uuid`.
3. **Direccion MAC**: Direccion de la tarjeta de red fisica principal.

El identificador final se genera mediante:
```
node_id = "node_" + SHA256(machine_id + ":" + product_uuid + ":" + mac_address + ":" + cluster_salt)[:16]
```

Este identificador se presenta al Hub en el handshake inicial y permanece inalterable aunque se reinicie el sistema o cambie la direccion IP dinamica.

---

## 3. Red y Comunicacion Segura

- **Canal de red**: Los satelites deben operar dentro de la red de area local (LAN privada) o a traves de la malla VPN cifrada punto a punto de **Tailscale** (`100.x.x.x`).
- **Autenticacion**: Todas las peticiones HTTP y eventos WebSocket al Hub requieren la cabecera `X-Jota-Token: <token_del_cluster>`.
- **Descubrimiento automatico (mDNS)**:
  - En redes locales compatibles con ZeroConf, el satelite detecta automaticamente la presencia del Hub buscando el servicio `_jota-hub._tcp.local.`.
  - Si mDNS esta deshabilitado o se utiliza una red enrutada como Tailscale, la IP o dominio del Hub se define de forma explicita.

---

## 4. Instalador Automatizado (install-satelite.sh)

El instalador configura las dependencias del sistema, el entorno virtual de Python, las reglas de permisos udev (para evdev) y el servicio de usuario de systemd.

### Sintaxis y Parametros

```bash
curl -fsSL https://raw.githubusercontent.com/jrodriiguezg/jota/satelite-0.1/install-satelite.sh | bash -s -- [OPCIONES]
```

O clonando el repositorio localmente:

```bash
git clone -b satelite-0.1 https://github.com/jrodriiguezg/jota.git ~/jota-satelite
cd ~/jota-satelite
./install-satelite.sh [OPCIONES]
```

### Tabla de Opciones del Instalador

| Parametro | Descripcion | Valor por Defecto |
| :--- | :--- | :--- |
| `--server-ip <IP_O_HOST>` | Direccion IP o nombre de host del Jota Hub | Auto-descubrimiento mDNS |
| `--server-token <TOKEN>` | Token secreto del cluster (`X-Jota-Token`) | Solicitar interactivamente |
| `--mode <desktop\|headless>` | Perfil de ejecucion (`desktop` o `headless`) | `desktop` |
| `--name <NOMBRE_NODO>` | Nombre amigable para identificar este nodo en el Hub | Nombre de hostname del host |
| `--server-port, --port <PUERTO>` | Puerto del Hub al que conectar | `8765` |
| `--unattended` | Modo no interactivo (requiere `--server-token`) | Desactivado |

### Ejemplos de Instalacion

#### Ejemplo 1: Estacion de trabajo interactiva (Perfil Desktop)
```bash
./install-satelite.sh \
  --server-ip 192.168.1.100 \
  --server-token mi_token_secreto \
  --mode desktop \
  --name "workstation-jota"
```

#### Ejemplo 2: Servidor secundario o NAS (Perfil Headless de Solo Lectura)
```bash
./install-satelite.sh \
  --server-ip 100.64.0.10 \
  --server-token mi_token_secreto \
  --mode headless \
  --name "servidor-truenas" \
  --unattended
```

---

## 5. Estructura de Configuracion (config/satelite.yaml)

Tras la instalacion, los parametros se almacenan en `~/.config/jota/satelite.yaml`:

```yaml
node:
  name: "workstation-jota"
  mode: "desktop"          # desktop | headless
  hardware_id: "auto"      # generado automaticamente mediante SHA256

hub:
  host: "192.168.1.100"    # IP local o IP de Tailscale
  port: 8765
  token: "mi_token_secreto"
  heartbeat_interval_sec: 15

audio:
  enabled: true            # false en modo headless
  stt_engine: "whisper"
  stt_model: "base"
  tts_engine: "piper"
  tts_voice: "es_ES-davefx-medium"

telemetry:
  enabled: true
  interval_sec: 30
  monitor_docker: true
  monitor_podman: false
  systemd_services:
    - "sshd"
    - "docker"
```

---

## 6. Gestion del Servicio del Satelite

El satelite se registra como un servicio de `systemd` que arranca con el sistema:

### En modo Desktop (Servicio de usuario graphical-session):
```bash
# Ver estado del satelite
systemctl --user status jota-satelite.service

# Reiniciar satelite
systemctl --user restart jota-satelite.service

# Seguir registros en tiempo real
journalctl --user -u jota-satelite.service -f
```

### En modo Headless (Servicio de sistema):
```bash
# Ver estado del satelite
sudo systemctl status jota-satelite.service

# Seguir registros en tiempo real
sudo journalctl -u jota-satelite.service -f
```

---

## 7. Verificacion y Pruebas

Para comprobar que el satelite y su identidad de hardware estan correctamente configurados:

```bash
# Inspeccionar identidad infalsificable del nodo y capacidades detectadas (CPU/GPU)
python3 -m jota.satellite --status

# Ejecutar satelite manualmente en primer plano para depuracion
python3 -m jota.satellite --mode desktop

# Ejecutar satelite en modo headless de telemetria
python3 -m jota.satellite --mode headless

# Ejecutar bateria de pruebas unitarias locales
pytest -q
```

