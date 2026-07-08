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
ZONES_STATE_FILE = "known_zones.json"
NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

# Cuadrícula de puntos (lat, lon, radio_metros) que cubre el área URBANA REAL
# de Valencia (los 19 distritos con densidad relevante de restaurantes; se
# excluyen las pedanías rurales del extremo norte/sur como Borbotó, Carpesa,
# El Saler o El Palmar, de muy baja densidad).
#
# Radios más pequeños en las zonas de más densidad de restaurantes
# (Ciutat Vella, Ruzafa, Eixample) para minimizar el riesgo de tocar el
# límite de 60 resultados de la API; radios más grandes en zonas más
# residenciales/periféricas.
GRID_POINTS = [
    # --- Núcleo denso (radio pequeño) ---
    {"label": "Ciutat Vella",           "lat": 39.4746, "lon": -0.3762, "radius": 700},
    {"label": "Ruzafa",                 "lat": 39.4629, "lon": -0.3729, "radius": 700},
    {"label": "Eixample / Gran Via",    "lat": 39.4660, "lon": -0.3660, "radius": 700},
    {"label": "Extramurs / El Carme",   "lat": 39.4720, "lon": -0.3850, "radius": 800},
    {"label": "Pla del Remei",          "lat": 39.4700, "lon": -0.3700, "radius": 700},

    # --- Densidad media ---
    {"label": "Benimaclet / Camí Vera", "lat": 39.4830, "lon": -0.3550, "radius": 1000},
    {"label": "Algirós",                "lat": 39.4800, "lon": -0.3620, "radius": 1000},
    {"label": "Malilla / Fuente S.Luis","lat": 39.4520, "lon": -0.3700, "radius": 1000},
    {"label": "Jesús",                  "lat": 39.4550, "lon": -0.3830, "radius": 1000},
    {"label": "Patraix",                "lat": 39.4570, "lon": -0.4000, "radius": 1000},
    {"label": "Campanar",               "lat": 39.4790, "lon": -0.4020, "radius": 1000},
    {"label": "Rascanya / Torrefiel",   "lat": 39.4930, "lon": -0.3800, "radius": 1100},

    # --- Poblados Marítimos (playa/puerto) — antes fuera de la cuadrícula ---
    {"label": "Cabanyal / Malvarrosa",  "lat": 39.4700, "lon": -0.3280, "radius": 1000},
    {"label": "El Grao / Puerto",       "lat": 39.4570, "lon": -0.3260, "radius": 1000},

    # --- Sur (Ciudad de las Artes, Quatre Carreres) — antes fuera de la cuadrícula ---
    {"label": "Quatre Carreres / CAC",  "lat": 39.4550, "lon": -0.3550, "radius": 1200},
    {"label": "Poblados del Sur",       "lat": 39.4380, "lon": -0.3680, "radius": 1500},

    # --- Oeste (Nou Moles, Benicalap) ---
    {"label": "Poblados del Oeste",     "lat": 39.4600, "lon": -0.4150, "radius": 1200},
    {"label": "Benicalap",              "lat": 39.4920, "lon": -0.3920, "radius": 1200},
]

# Umbral a partir del cual avisamos de que una zona probablemente está
# tocando el límite de 60 resultados de la API (y por tanto perdiendo datos).
CAP_WARNING_THRESHOLD = 55


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

    if len(results) >= CAP_WARNING_THRESHOLD:
        print(
            f"[AVISO] '{point['label']}' devolvió {len(results)} resultados "
            f"(cerca del límite de 60 de Google) — probablemente se están "
            f"perdiendo restaurantes en esta zona. Considera reducir el radio "
            f"o añadir más puntos aquí."
        )

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


def load_known_zones() -> set[str]:
    if os.path.exists(ZONES_STATE_FILE):
        with open(ZONES_STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_known_zones(zones: set[str]) -> None:
    with open(ZONES_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(zones), f, ensure_ascii=False, indent=2)


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

    current_zones = {p["label"] for p in GRID_POINTS}
    known_zones = load_known_zones()
    # Zonas que se han añadido a la cuadrícula desde la última ejecución.
    # known_zones vacío = o bien es la primerísima vez que corre el bot, o
    # bien viene de antes de que existiera este archivo: en ese caso no
    # sabemos qué zonas ya se cubrían, así que no tratamos ninguna como
    # "nueva" (evita falsos positivos de silenciado).
    new_zones = current_zones - known_zones if known_zones else set()

    print(f"Restaurantes encontrados hoy: {len(current_ids)}")
    print(f"Restaurantes conocidos (state.json): {len(known_ids)}")
    if new_zones:
        print(f"Zonas nuevas en la cuadrícula esta vez: {sorted(new_zones)}")

    new_ids = current_ids - known_ids
    if new_ids and known_ids:  # known_ids vacío = primera ejecución, no avisar de "todos"
        new_places = [p for p in current if p["place_id"] in new_ids]

        if new_zones:
            de_zonas_nuevas = [p for p in new_places if p.get("_zone") in new_zones]
            new_places = [p for p in new_places if p.get("_zone") not in new_zones]
            if de_zonas_nuevas:
                print(
                    f"{len(de_zonas_nuevas)} restaurantes encontrados solo porque "
                    f"su zona es nueva en la cuadrícula (no son aperturas reales, "
                    f"no se avisa por email; se guardan igualmente en state.json)."
                )

        if new_places:
            print(f"Encontrados {len(new_places)} restaurantes nuevos. Enviando email...")
            try:
                send_email(new_places)
            except Exception as e:
                print(f"Error al enviar email: {e}", file=sys.stderr)
        else:
            print("Sin restaurantes genuinamente nuevos.")
    else:
        print("Sin novedades.")

    save_known_ids(current_ids)
    save_known_zones(current_zones)


if __name__ == "__main__":
    main()
