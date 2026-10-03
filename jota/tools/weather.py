"""Consulta meteorologica mediante API publica de Open-Meteo sin necesidad de API key."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Mapeo de codigos WMO de la OMM a descripcion en espanol
WMO_CODES = {
    0: "despejado con cielo soleado",
    1: "principalmente despejado",
    2: "parcialmente nublado",
    3: "cubierto de nubes",
    45: "con niebla",
    48: "con niebla engelante",
    51: "llovizna ligera",
    53: "llovizna moderada",
    55: "llovizna densa",
    61: "lluvia debil",
    63: "lluvia moderada",
    65: "lluvia fuerte",
    71: "nieve ligera",
    73: "nieve moderada",
    75: "nieve intensa",
    80: "chubascos dispersos",
    81: "chubascos moderados",
    82: "chubascos violentos",
    95: "tormenta electrica",
    96: "tormenta con granizo ligero",
    99: "tormenta con granizo fuerte",
}


def get_weather(city: str = "Madrid") -> tuple[bool, str]:
    """Obtiene el tiempo actual para la ciudad especificada usando Open-Meteo."""
    clean_city = city.strip() or "Madrid"
    try:
        # 1. Geocodificacion de la ciudad
        geo_url = (
            f"https://geocoding-api.open-meteo.com/v1/search?name={clean_city}&count=1&language=es"
        )
        with httpx.Client(timeout=4.0) as client:
            geo_resp = client.get(geo_url)
            if geo_resp.status_code != 200:
                return False, f"No se pudo localizar la ciudad {clean_city}."

            geo_data = geo_resp.json()
            results = geo_data.get("results")
            if not results:
                return False, f"No se encontro ninguna ubicacion para {clean_city}."

            location = results[0]
            lat = location.get("latitude")
            lon = location.get("longitude")
            place_name = location.get("name", clean_city)
            country = location.get("country", "")

            # 2. Consulta del tiempo actual
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                "&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code"
            )
            w_resp = client.get(weather_url)
            if w_resp.status_code != 200:
                return False, f"Error al consultar datos meteorologicos para {place_name}."

            w_data: dict[str, Any] = w_resp.json()
            current = w_data.get("current", {})

            temp = current.get("temperature_2m")
            feel = current.get("apparent_temperature")
            humidity = current.get("relative_humidity_2m")
            precip = current.get("precipitation", 0.0)
            code = current.get("weather_code", 0)

            desc = WMO_CODES.get(code, "tiempo variable")
            location_str = f"{place_name}, {country}" if country else place_name

            msg = (
                f"En {location_str} el cielo esta {desc}, "
                f"con una temperatura de {temp} grados (sensacion de {feel} grados) "
                f"y una humedad del {humidity}%."
            )
            if precip > 0:
                msg += f" Precipitacion actual de {precip} mm."

            return True, msg

    except Exception as e:
        logger.error("Error consultando el tiempo para %s: %s", clean_city, e)
        return False, f"Error al consultar el tiempo: {e}"
