import logging
import random
import aiohttp
from datetime import datetime, timedelta, timezone
from config import URL_WEATHER

# Logger für dieses Modul
logger = logging.getLogger(__name__)


class WeatherService:
    def __init__(self, url: str = URL_WEATHER):
        self.url = url
        self.raw_data = None
        self.formatted_data = None

    async def update(self) -> bool:
        """
        Holt frische Wetterdaten asynchron ab und verarbeitet sie direkt.
        Gibt True bei Erfolg zurück, sonst False.
        """
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(self.url, timeout=15) as resp:
                    if resp.status == 200:
                        self.raw_data = await resp.json()
                        self._process_data()
                        logger.info("Wetterdaten erfolgreich aktualisiert.")
                        return True
                    else:
                        logger.error(f"⚠️ Wetter-Abruf fehlgeschlagen: Status {resp.status} ({resp.reason})")
                        return False
            except Exception as e:
                logger.critical(f"🚨 KRITISCHER FEHLER beim Wetter-Abruf: {type(e).__name__}: {e}")
                return False

    def _process_data(self):
        """Bereitet die Rohdaten für das Bild-Overlay auf."""
        if not self.raw_data:
            return

        cw = self.raw_data.get("current", {})
        elevation = self.raw_data.get("elevation", 0)
        offset_seconds = self.raw_data.get("utc_offset_seconds", 0)
        tz_info = timezone(timedelta(seconds=offset_seconds))

        # Zeitstempel verarbeiten
        raw_time = cw.get("time")
        try:
            dt_local = datetime.fromisoformat(raw_time).replace(tzinfo=tz_info)
        except (ValueError, TypeError):
            dt_local = datetime.now(tz_info)

        # Wetterdaten extrahieren
        temp = cw.get("temperature_2m")
        feels = cw.get("apparent_temperature")
        wind = cw.get("wind_speed_10m")
        gusts = cw.get("wind_gusts_10m")
        humidity = cw.get("relative_humidity_2m")
        pressure = cw.get("pressure_msl")
        precip = cw.get("precipitation", 0)
        cloud_cover = cw.get("cloud_cover", 0)
        code = cw.get("weather_code")
        is_day = cw.get("is_day", 1)

        # WMO Code zu Text und Icon wandeln
        icon, text = self._get_wmo_info(code, is_day)

        # Kompaktes Dictionary für das Overlay bauen
        self.formatted_data = {
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
            "precipitation": f"Niederschlag: {precip} mm",
            "clouds": f"Bewölkung: {cloud_cover} %",
            "is_day": is_day,
            "raw_code": code
        }

    def _get_wmo_info(self, code: int, is_day: int) -> tuple:
        """Übersetzt WMO-Wettercodes in Symbole und Beschreibungen."""
        if code == 0:
            return ("☀️", "Klarer Himmel") if is_day else ("✨", "Sternenklar")
        elif code in (1, 2, 3):
            return ("🌤️", "Leicht bewölkt") if is_day else ("☁️", "Bewölkt")
        elif code in (45, 48):
            return ("🌫️", "Nebel")
        elif code in (51, 53, 55):
            return ("🌦️", "Nieselregen") if is_day else ("🌧️", "Nieselregen")
        elif code in (56, 57):
            return ("🌨️", "Gefrierender Niesel")
        elif code in (61, 63, 65):
            return ("🌧️", "Regen")
        elif code in (66, 67):
            return ("🧊", "Gefrierender Regen")
        elif code in (71, 73, 75):
            return ("❄️", "Schneefall")
        elif code == 77:
            return ("⚪", "Schneegriesel")
        elif code in (80, 81, 82):
            return ("🌦️", "Regenschauer") if is_day else ("🌧️", "Regenschauer")
        elif code in (85, 86):
            return ("🌨️", "Schneeschauer")
        elif code in (95, 96, 99):
            return ("⛈️", "Gewitter")
        return ("❓", f"Unbekannt ({code})")

    def compute_next_wait_seconds(self) -> float:
        """
        Berechnet die Wartezeit bis zum nächsten API-Update basierend auf dem
        Intervall der Open-Meteo API (inkl. Puffer und Zufall).
        """
        if not self.raw_data:
            return 900.0 + random.uniform(10, 20)

        cw = self.raw_data.get("current", {})
        api_time_str = cw.get("time")
        api_interval = cw.get("interval", 900)
        offset_seconds = self.raw_data.get("utc_offset_seconds", 0)

        if not api_time_str:
            return 900.0

        # Zeitberechnung (Lokal -> UTC -> Next Update)
        local_api_dt = datetime.fromisoformat(api_time_str)
        api_utc_dt = (local_api_dt - timedelta(seconds=offset_seconds)).replace(tzinfo=timezone.utc)
        next_update_utc = api_utc_dt + timedelta(seconds=api_interval)

        now_utc = datetime.now(timezone.utc)
        remaining_seconds = (next_update_utc - now_utc).total_seconds()

        # Puffer hinzufügen, um nicht zu früh anzufragen
        total_wait = remaining_seconds + random.uniform(15.0, 30.0)

        return max(total_wait, 20.0)