"""
Detecta restaurantes nuevos en Valencia usando Google Places API
y envía un email cuando aparece alguno que no se había visto antes.

Busca por una CUADRÍCULA de puntos repartidos por la ciudad (en vez de una
única búsqueda) para conseguir cobertura real de todas las zonas, ya que
Google limita cada búsqueda a 60 resultados.

Variables de entorno necesarias:
  GOOGLE_API_KEY   -> API key de Google Cloud con Places API activada
  EMAIL_FROM        -> email remitente (ej. tunombre@gmail.com)
  EMAIL_PASSWORD    -> contraseña de aplicación del email remitente
  EMAIL_TO          -> email donde quieres recibir el aviso
  SMTP_SERVER       -> ej. smtp.gmail.com
  SMTP_PORT         -> ej. 587
"""

import json
import os
import smtplib
import sys
import time
from email.mime.text import MIMEText

import requests

STATE_FILE = "state.json"
NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

# Cuadrícula de puntos (lat, lon, radio_metros) que cubre el área urbana de
# Valencia. Los radios se solapan ligeramente entre puntos vecinos para no
# dejar huecos. Ajusta/añade puntos si quieres más o menos cobertura.
GRID_POINTS = [
    {"label": "Zona 1 (Noroeste)",  "lat": 39.4880, "lon": -0.4050, "radius": 1300},
    {"label": "Zona 2 (Norte)",     "lat": 39.4880, "lon": -0.3750, "radius": 1300},
    {"label": "Zona 3 (Noreste)",   "lat": 39.4880, "lon": -0.3450, "radius": 1300},
    {"label": "Zona 4 (Oeste)",     "lat": 39.4730, "lon": -0.4050, "radius": 1300},
    {"label": "Zona 5 (Centro)",    "lat": 39.4730, "lon": -0.3750, "radius": 1300},
    {"label": "Zona 6 (Este)",      "lat": 39.4730, "lon": -0.3450, "radius": 1300},
    {"label": "Zona 7 (Suroeste)",  "lat": 39.4580, "lon": -0.4050, "radius": 1300},
    {"label": "Zona 8 (Sur)",       "lat": 39.4580, "lon": -0.3750, "radius": 1300},
    {"label": "Zona 9 (Sureste)",   "lat": 39.4580, "lon": -0.3450, "radius": 1300},
]


def fetch_grid_point(api_key: str, point: dict) -> list[dict]:
    """Trae hasta 60 resultados (límite de Google) alrededor de un punto."""
    results = []
    params = {
        "location": f"{point['lat']},{point['lon']}",
        "radius": point["radius"],
        "type": "restaurant",
        "key": api_key,
    }
    next_token = None

    for _ in range(3):  # Google permite máximo 3 páginas (20 cada una)
        if next_token:
            params = {"pagetoken": next_token, "key": api_key}
            time.sleep(2)  # el next_page_token tarda un par de segundos en activarse
        resp = requests.get(NEARBY_URL, params=params, timeout=15)
        data = resp.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            print(f"Error de la API en {point['label']}: {data.get('status')}")
            break

        for r in data.get("results", []):
            r["_zone"] = point["label"]
        results.extend(data.get("results", []))

        next_token = data.get("next_page_token")
        if not next_token:
            break

    return results


def fetch_restaurants(api_key: str) -> list[dict]:
    """Recorre toda la cuadrícula y devuelve resultados sin duplicados."""
    seen_ids = set()
    all_results = []
    for point in GRID_POINTS:
        for r in fetch_grid_point(api_key, point):
            pid = r.get("place_id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_results.append(r)
    return all_results


def load_known_ids() -> set[str]:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_known_ids(ids: set[str]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, ensure_ascii=False, indent=2)


def send_email(new_places: list[dict]) -> None:
    by_zone: dict[str, list[dict]] = {}
    for p in new_places:
        by_zone.setdefault(p.get("_zone", "Zona desconocida"), []).append(p)

    blocks = []
    for zone, places in sorted(by_zone.items()):
        lines = []
        for p in places:
            name = p.get("name", "Sin nombre")
            address = p.get("vicinity", "")
            rating = p.get("rating", "sin valorar")
            lines.append(f"  - {name} ({address}) — rating: {rating}")
        blocks.append(f"{zone}:\n" + "\n".join(lines))

    body = "Se han detectado nuevos restaurantes en Valencia:\n\n" + "\n\n".join(blocks)
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = f"🍽️ {len(new_places)} restaurante(s) nuevo(s) en Valencia"
    msg["From"] = os.environ["EMAIL_FROM"]
    msg["To"] = os.environ["EMAIL_TO"]

    with smtplib.SMTP(os.environ["SMTP_SERVER"], int(os.environ["SMTP_PORT"])) as server:
        server.starttls()
        server.login(os.environ["EMAIL_FROM"], os.environ["EMAIL_PASSWORD"])
        server.send_message(msg)


def main() -> None:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Falta GOOGLE_API_KEY", file=sys.stderr)
        sys.exit(1)

    current = fetch_restaurants(api_key)
    current_ids = {p["place_id"] for p in current if "place_id" in p}
    known_ids = load_known_ids()

    new_ids = current_ids - known_ids
    if new_ids and known_ids:  # known_ids vacío = primera ejecución, no avisar de "todos"
        new_places = [p for p in current if p["place_id"] in new_ids]
        print(f"Encontrados {len(new_places)} restaurantes nuevos. Enviando email...")
        send_email(new_places)
    else:
        print("Sin novedades.")

    save_known_ids(current_ids)


if __name__ == "__main__":
    main()
