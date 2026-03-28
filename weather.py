import logging
import random

import aiohttp
from datetime import datetime, timedelta, timezone
from config import URL_WEATHER

# Logger für dieses Modul initialisieren
logger = logging.getLogger(__name__)

async def fetch_weather():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(URL_WEATHER, timeout=10) as resp:
                # Prüft, ob der Status-Code 200-299 ist
                if resp.status == 200:
                    return await resp.json()
                else:
                    # Fehlermeldung direkt in die Konsole
                    logger.error(f"⚠️ FEHLER beim Wetter-Abruf: Status {resp.status} ({resp.reason})")
                    return None
        except Exception as e:
            # Fängt Timeouts oder Verbindungsfehler ab
            logger.critical(f"🚨 KRITISCHER FEHLER beim Wetter-Abruf: {type(e).__name__}: {e}")
            return None


def compute_next_wait_seconds(data: dict) -> float:
    cw = data.get("current", {})
    api_time_str = cw.get("time")  # z.B. "2026-03-27T12:45"
    api_interval = cw.get("interval", 900)

    # Der Offset von der API (z.B. 3600 für Berlin/Winterzeit)
    offset_seconds = data.get("utc_offset_seconds", 0)

    if not api_time_str:
        return 900.0 + random.uniform(10, 20)

    # 1. API-Zeit als "naive" Zeit parsen
    local_api_dt = datetime.fromisoformat(api_time_str)
    logger.info(f"time: {api_time_str}, interval: {api_interval}, offset_seconds: {offset_seconds}")
    # 2. In echte UTC-Zeit umrechnen:
    # Wenn die API 12:45 bei einem Offset von 3600s schickt,
    # ist es in UTC eigentlich 11:45.
    api_utc_dt = (local_api_dt - timedelta(seconds=offset_seconds)).replace(tzinfo=timezone.utc)

    # 3. Nächstes Update (in UTC)
    next_update_utc = api_utc_dt + timedelta(seconds=api_interval)

    # 4. Aktuelle Zeit (UTC)
    now_utc = datetime.now(timezone.utc)

    # 5. Differenz
    remaining_seconds = (next_update_utc - now_utc).total_seconds()

    # 6. Puffer (10 bis 25 Sekunden)
    puffer = random.uniform(10.0, 25.0)
    total_wait = remaining_seconds + puffer

    # Sicherheits-Check
    if total_wait < 10:
        return 15.0

    return total_wait


def format_weather(data: dict) -> dict:
    cw = data.get("current", {})
    elevation = data.get("elevation", 0)
    # Zeitstempel von der API (z.B. "2024-03-26T21:30")
    raw_time = cw.get("time")

    # Offset in Sekunden holen (z.B. 3600 für Winterzeit, 7200 für Sommerzeit)
    offset_seconds = data.get("utc_offset_seconds", 0)
    tz_info = timezone(timedelta(seconds=offset_seconds))

    # In datetime umwandeln und Zeitzone zuweisen
    try:
        # Wir parsen die Zeit und hängen die Zeitzone des Offsets an
        dt_local = datetime.fromisoformat(raw_time).replace(tzinfo=tz_info)
    except:
        dt_local = datetime.now(tz_info)

    # Wetterdaten extrahieren
    temp = cw.get("temperature_2m")
    feels = cw.get("apparent_temperature")
    wind = cw.get("wind_speed_10m")
    gusts = cw.get("wind_gusts_10m")
    humidity = cw.get("relative_humidity_2m")
    pressure = cw.get("pressure_msl")
    code = cw.get("weather_code")
    wind_dir = cw.get("wind_direction_10m")

    # Tag/Nacht-Erkennung (1 = Tag, 0 = Nacht)
    is_day = cw.get("is_day", 1)

    # WMO Wettercodes mit Tag/Nacht-Logik
    if code == 0:
        icon, text = ("☀️", "Klarer Himmel") if is_day else ("✨", "Sternenklar")
    elif code in (1, 2, 3):
        # 1=Klar, 2=Teils wolkig, 3=Bedeckt
        icon, text = ("🌤️", "Leicht bewölkt") if is_day else ("☁️", "Bewölkt")
    elif code in (45, 48):
        icon, text = "🌫️", "Nebel"
    elif code in (51, 53, 55):
        icon, text = ("🌦️", "Nieselregen") if is_day else ("🌧️", "Nieselregen")
    elif code in (56, 57):
        icon, text = "🌨️", "Gefrierender Niesel"
    elif code in (61, 63, 65):
        icon, text = "🌧️", "Regen"
    elif code in (66, 67):
        icon, text = "🧊", "Gefrierender Regen"
    elif code in (71, 73, 75):
        icon, text = "❄️", "Schneefall"
    elif code == 77:
        icon, text = "⚪", "Schneegriesel"
    elif code in (80, 81, 82):
        icon, text = ("🌦️", "Regenschauer") if is_day else ("🌧️", "Regenschauer")
    elif code in (85, 86):
        icon, text = "🌨️", "Schneeschauer"
    elif code in (95, 96, 99):
        icon, text = "⛈️", "Gewitter"
    else:
        icon, text = "❓", f"Unbekannt ({code})"

    return {
        "datetime": dt_local,
        "icon": icon,
        "text": text,
        "elevation": f"{int(elevation)} m ü. NHN",
        "temp": f"{temp:.1f} °C" if temp is not None else "-- °C",
        "feels": f"Gefühlt {feels:.1f} °C" if feels is not None else "Gefühlt -- °C",
        "wind": f"Wind: {wind} km/h" if wind is not None else "Wind: -- km/h",
        "gusts": f"Böen: {gusts} km/h" if gusts is not None else "Böen: -- km/h",
        "humidity": f"Feuchte: {humidity} %" if humidity is not None else "Feuchte: -- %",
        "pressure": f"Druck: {pressure} hPa" if pressure is not None else "Druck: -- hPa",
        "wind_dir": wind_dir,
        "is_day": is_day,  # Für spätere Verwendung im Overlay mitgeben
        "raw": cw,
    }