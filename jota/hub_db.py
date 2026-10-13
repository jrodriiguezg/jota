"""
Base de datos SQLite y capa de persistencia para Jota Hub.
Gestiona el registro del cluster de nodos, telemetria multi-servidor,
deteccion de servidores secundarios con GPU y almacenamiento cifrado de secretos.
"""

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from jota.crypto import decrypt_string, encrypt_string

logger = logging.getLogger("jota.hub_db")

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'desktop',
    hardware_fingerprint TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 8765,
    status TEXT NOT NULL DEFAULT 'online',
    is_gpu_worker INTEGER NOT NULL DEFAULT 0,
    gpu_info TEXT DEFAULT '',
    last_heartbeat REAL NOT NULL,
    registered_at REAL NOT NULL,
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS node_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    cpu_percent REAL DEFAULT 0.0,
    ram_percent REAL DEFAULT 0.0,
    ram_used_mb REAL DEFAULT 0.0,
    ram_total_mb REAL DEFAULT 0.0,
    disk_percent REAL DEFAULT 0.0,
    disk_free_gb REAL DEFAULT 0.0,
    containers_json TEXT DEFAULT '[]',
    systemd_services_json TEXT DEFAULT '[]',
    FOREIGN KEY (node_id) REFERENCES nodes(node_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_telemetry_node_time ON node_telemetry(node_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS cluster_secrets (
    key TEXT PRIMARY KEY,
    encrypted_value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


class HubDatabase:
    """Gestor de base de datos SQLite para Jota Hub."""

    def __init__(self, db_path: Path | str, secret_key: str = "jota-cluster-secret"):
        self.db_path = Path(db_path)
        self.secret_key = secret_key
        self._ensure_secure_storage()
        self.init_schema()

    def _ensure_secure_storage(self) -> None:
        """Asegura que el directorio y archivo de base de datos tengan permisos restringidos (0700/0600)."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.db_path.parent.chmod(0o700)
            if self.db_path.exists():
                self.db_path.chmod(0o600)
        except (PermissionError, OSError) as e:
            logger.debug("No se pudieron ajustar permisos POSIX de base de datos: %s", e)

    def _get_connection(self) -> sqlite3.Connection:
        """Abre conexion a SQLite con row_factory como sqlite3.Row."""
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        """Inicializa las tablas e indices de la base de datos."""
        with self._get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
        try:
            if self.db_path.exists():
                self.db_path.chmod(0o600)
        except (PermissionError, OSError):
            pass

    def register_or_update_node(
        self,
        node_id: str,
        name: str,
        mode: str,
        hardware_fingerprint: str,
        ip_address: str,
        port: int = 8765,
        is_gpu_worker: bool = False,
        gpu_info: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """
        Registra un nuevo satelite o actualiza uno existente.
        Valida que la huella de hardware coincida para impedir suplantaciones.
        """
        if not node_id or not node_id.startswith("node_"):
            return False, "Identificador de nodo con formato invalido."

        if not hardware_fingerprint or len(hardware_fingerprint) != 64:
            return False, "Huella de hardware invalida (debe ser hash SHA-256 de 64 caracteres)."

        now = time.time()
        metadata_str = json.dumps(metadata or {}, ensure_ascii=False)

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT hardware_fingerprint, name FROM nodes WHERE node_id = ?", (node_id,))
            row = cur.fetchone()

            if row:
                existing_fp = row["hardware_fingerprint"]
                if existing_fp != hardware_fingerprint:
                    logger.warning(
                        "Alerta de seguridad: intento de registro de %s con huella invalida (esperada %s, recibida %s)",
                        node_id,
                        existing_fp[:8],
                        hardware_fingerprint[:8],
                    )
                    return (
                        False,
                        f"Conflicto de hardware: el nodo '{node_id}' ya esta registrado con una huella distinta.",
                    )

                # Actualizar nodo existente
                cur.execute(
                    """
                    UPDATE nodes
                    SET name = ?, mode = ?, ip_address = ?, port = ?, status = 'online',
                        is_gpu_worker = ?, gpu_info = ?, last_heartbeat = ?, metadata_json = ?
                    WHERE node_id = ?
                    """,
                    (
                        name,
                        mode,
                        ip_address,
                        port,
                        1 if is_gpu_worker else 0,
                        gpu_info,
                        now,
                        metadata_str,
                        node_id,
                    ),
                )
                conn.commit()
                return True, f"Nodo '{node_id}' ({name}) actualizado exitosamente."
            else:
                # Insertar nuevo nodo
                cur.execute(
                    """
                    INSERT INTO nodes (
                        node_id, name, mode, hardware_fingerprint, ip_address, port,
                        status, is_gpu_worker, gpu_info, last_heartbeat, registered_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, 'online', ?, ?, ?, ?, ?)
                    """,
                    (
                        node_id,
                        name,
                        mode,
                        hardware_fingerprint,
                        ip_address,
                        port,
                        1 if is_gpu_worker else 0,
                        gpu_info,
                        now,
                        now,
                        metadata_str,
                    ),
                )
                conn.commit()
                return True, f"Nodo '{node_id}' ({name}) registrado exitosamente."

    def record_heartbeat(
        self,
        node_id: str,
        ip_address: str | None = None,
        is_gpu_worker: bool | None = None,
        gpu_info: str | None = None,
    ) -> bool:
        """Actualiza la marca de tiempo de ultimo latido y estado activo del nodo."""
        now = time.time()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT node_id FROM nodes WHERE node_id = ?", (node_id,))
            if not cur.fetchone():
                return False

            updates = ["last_heartbeat = ?", "status = 'online'"]
            params: list[Any] = [now]

            if ip_address:
                updates.append("ip_address = ?")
                params.append(ip_address)
            if is_gpu_worker is not None:
                updates.append("is_gpu_worker = ?")
                params.append(1 if is_gpu_worker else 0)
            if gpu_info is not None:
                updates.append("gpu_info = ?")
                params.append(gpu_info)

            params.append(node_id)
            query = f"UPDATE nodes SET {', '.join(updates)} WHERE node_id = ?"
            cur.execute(query, params)
            conn.commit()
            return True

    def record_telemetry(self, node_id: str, telemetry: dict[str, Any]) -> bool:
        """Registra un reporte de telemetria recibido de un satelite."""
        now = time.time()
        containers_json = json.dumps(telemetry.get("containers", []), ensure_ascii=False)
        systemd_json = json.dumps(telemetry.get("systemd_services", []), ensure_ascii=False)

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO node_telemetry (
                    node_id, timestamp, cpu_percent, ram_percent, ram_used_mb,
                    ram_total_mb, disk_percent, disk_free_gb, containers_json, systemd_services_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    now,
                    float(telemetry.get("cpu_percent", 0.0)),
                    float(telemetry.get("ram_percent", 0.0)),
                    float(telemetry.get("ram_used_mb", 0.0)),
                    float(telemetry.get("ram_total_mb", 0.0)),
                    float(telemetry.get("disk_percent", 0.0)),
                    float(telemetry.get("disk_free_gb", 0.0)),
                    containers_json,
                    systemd_json,
                ),
            )
            # Actualizar tambien el latido del nodo
            cur.execute(
                "UPDATE nodes SET last_heartbeat = ?, status = 'online' WHERE node_id = ?",
                (now, node_id),
            )
            # Conservar solo los ultimos 100 reportes por nodo para no inflar la base de datos
            cur.execute(
                """
                DELETE FROM node_telemetry
                WHERE node_id = ? AND id NOT IN (
                    SELECT id FROM node_telemetry WHERE node_id = ? ORDER BY timestamp DESC LIMIT 100
                )
                """,
                (node_id, node_id),
            )
            conn.commit()
            return True

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Obtiene un nodo por su node_id."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
            row = cur.fetchone()
            if not row:
                return None
            return dict(row)

    def list_nodes(self, offline_timeout_seconds: float = 45.0) -> list[dict[str, Any]]:
        """
        Lista todos los nodos y calcula dinamicamente si estan online u offline
        segun la antiguedad de su ultimo heartbeat.
        """
        now = time.time()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM nodes ORDER BY name ASC")
            rows = cur.fetchall()
            result = []
            for r in rows:
                item = dict(r)
                is_stale = (now - item["last_heartbeat"]) > offline_timeout_seconds
                item["status"] = "offline" if is_stale else "online"
                try:
                    item["metadata"] = json.loads(item.get("metadata_json") or "{}")
                except Exception:
                    item["metadata"] = {}
                result.append(item)
            return result

    def get_active_gpu_worker(self, offline_timeout_seconds: float = 45.0) -> dict[str, Any] | None:
        """
        Devuelve el servidor secundario con GPU activo y disponible para offload,
        o None si no hay ninguno conectado.
        """
        now = time.time()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM nodes
                WHERE is_gpu_worker = 1
                ORDER BY last_heartbeat DESC
                """
            )
            rows = cur.fetchall()
            for r in rows:
                item = dict(r)
                if (now - item["last_heartbeat"]) <= offline_timeout_seconds:
                    item["status"] = "online"
                    return item
            return None

    def get_latest_telemetry(self, node_id: str) -> dict[str, Any] | None:
        """Devuelve el reporte de telemetria mas reciente de un nodo."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM node_telemetry
                WHERE node_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (node_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            data = dict(row)
            try:
                data["containers"] = json.loads(data.get("containers_json") or "[]")
                data["systemd_services"] = json.loads(data.get("systemd_services_json") or "[]")
            except Exception:
                data["containers"] = []
                data["systemd_services"] = []
            return data

    def get_all_containers_summary(self, offline_timeout_seconds: float = 60.0) -> list[dict[str, Any]]:
        """
        Consolida la lista de contenedores Docker/Podman de todos los nodos activos.
        """
        nodes = self.list_nodes(offline_timeout_seconds=offline_timeout_seconds)
        all_containers = []
        for n in nodes:
            telemetry = self.get_latest_telemetry(n["node_id"])
            if telemetry and "containers" in telemetry:
                for c in telemetry["containers"]:
                    c_copy = dict(c)
                    c_copy["node_id"] = n["node_id"]
                    c_copy["node_name"] = n["name"]
                    c_copy["node_ip"] = n["ip_address"]
                    c_copy["node_status"] = n["status"]
                    all_containers.append(c_copy)
        return all_containers

    def set_secret(self, key: str, value: str) -> None:
        """Almacena un secreto en la base de datos cifrado con AES-256-GCM."""
        enc_value = encrypt_string(value, self.secret_key)
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cluster_secrets (key, encrypted_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET encrypted_value = excluded.encrypted_value, updated_at = excluded.updated_at
                """,
                (key, enc_value, now),
            )
            conn.commit()

    def get_secret(self, key: str) -> str | None:
        """Obtiene y descifra un secreto almacenado en la base de datos."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT encrypted_value FROM cluster_secrets WHERE key = ?", (key,))
            row = cur.fetchone()
            if not row:
                return None
            return decrypt_string(row["encrypted_value"], self.secret_key)
