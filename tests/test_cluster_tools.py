"""
Pruebas unitarias para las herramientas del cluster multi-servidor (jota.tools.cluster).
"""

from unittest.mock import MagicMock, patch

from jota.tools.cluster import (
    query_cluster_containers,
    query_cluster_nodes,
    query_node_telemetry,
)
from jota.tools.router import execute_tool, match_fast_intent, parse_llm_tool_call


def test_query_cluster_nodes_empty():
    """Verifica respuesta adecuada cuando no hay nodos registrados."""
    mock_db = MagicMock()
    mock_db.list_nodes.return_value = []
    with patch("jota.tools.cluster._get_hub_db", return_value=mock_db):
        ok, msg = query_cluster_nodes()
        assert ok is True
        assert "No hay ningun nodo" in msg


def test_query_cluster_nodes_with_workers():
    """Verifica formateo natural de servidores activos con GPU."""
    mock_db = MagicMock()
    mock_db.list_nodes.return_value = [
        {
            "node_id": "node_1",
            "name": "workstation-gpu",
            "status": "online",
            "mode": "desktop",
            "is_gpu_worker": 1,
            "gpu_info": "NVIDIA RTX 5070",
        },
        {
            "node_id": "node_2",
            "name": "truenas-core",
            "status": "online",
            "mode": "headless",
            "is_gpu_worker": 0,
            "gpu_info": "",
        },
    ]
    with patch("jota.tools.cluster._get_hub_db", return_value=mock_db):
        ok, msg = query_cluster_nodes()
        assert ok is True
        assert "workstation-gpu" in msg
        assert "RTX 5070" in msg
        assert "truenas-core" in msg


def test_query_node_telemetry():
    """Verifica consulta de metricas de un nodo especifico."""
    mock_db = MagicMock()
    mock_db.list_nodes.return_value = [
        {"node_id": "node_nas", "name": "servidor-nas"}
    ]
    mock_db.get_latest_telemetry.return_value = {
        "cpu_percent": 18.2,
        "ram_percent": 55.0,
        "disk_percent": 74.0,
        "containers": [
            {"name": "navidrome", "status": "running"},
            {"name": "jellyfin", "status": "running"},
        ],
    }
    with patch("jota.tools.cluster._get_hub_db", return_value=mock_db):
        ok, msg = query_node_telemetry("servidor-nas")
        assert ok is True
        assert "18.2%" in msg
        assert "55.0%" in msg
        assert "2 de 2 contenedores" in msg


def test_query_cluster_containers():
    """Verifica consolidacion y filtrado de contenedores del cluster."""
    mock_db = MagicMock()
    mock_db.get_all_containers_summary.return_value = [
        {"name": "navidrome", "node_name": "nas", "status": "running"},
        {"name": "vaultwarden", "node_name": "hub", "status": "running"},
    ]
    with patch("jota.tools.cluster._get_hub_db", return_value=mock_db):
        ok, msg = query_cluster_containers()
        assert ok is True
        assert "navidrome en nas" in msg
        assert "vaultwarden en hub" in msg


def test_router_fast_intent_for_cluster():
    """Verifica reconocimiento inmediato de intenciones del cluster."""
    intent1 = match_fast_intent("que servidores estan activos")
    assert intent1 is not None
    assert intent1[0] == "cluster_nodes"

    intent2 = match_fast_intent("estado del servidor nas")
    assert intent2 is not None
    assert intent2[0] == "cluster_node_telemetry"
    assert intent2[1]["name"] == "nas"

    intent3 = match_fast_intent("contenedores del cluster")
    assert intent3 is not None
    assert intent3[0] == "cluster_containers"


def test_router_parse_and_execute_cluster_tool():
    """Verifica parseo y ejecucion de la herramienta por el router."""
    parsed = parse_llm_tool_call("TOOL: cluster_nodes(status='all')")
    assert parsed is not None
    assert parsed[0] == "cluster_nodes"

    mock_db = MagicMock()
    mock_db.list_nodes.return_value = []
    with patch("jota.tools.cluster._get_hub_db", return_value=mock_db):
        ok, msg = execute_tool("cluster_nodes", {"status": "all"})
        assert ok is True
        assert "No hay ningun nodo" in msg
