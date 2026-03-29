# telegram_sender.py

import asyncio
import logging
import time
from io import BytesIO

from telegram import Bot
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def telegram_enabled():
    """Prüft, ob Telegram korrekt konfiguriert ist."""
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


async def send_telegram_photo(img_pil, caption=""):
    """Sendet ein PIL-Bild direkt an Telegram."""
    if not telegram_enabled():
        logger.warning("Telegram nicht konfiguriert – kein Versand.")
        return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    bio = BytesIO()
    img_pil.save(bio, format="JPEG")
    bio.seek(0)

    try:
        await bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=bio,
            caption=caption
        )
        logger.info("Telegram-Bild erfolgreich gesendet.")
    except Exception as e:
        logger.error(f"Telegram-Versand fehlgeschlagen: {e}")


async def telegram_loop(viewer):
    """
    Sendet das erste Bild sofort nach Programmstart und danach
    jeweils 1 Minute nach der vollen Stunde.
    """
    if not telegram_enabled():
        logger.info("Telegram deaktiviert – Loop wird nicht gestartet.")
        return

    """
    await asyncio.sleep(5)
    if viewer.last_raw_image is not None:
        await send_current_viewer_image(viewer)
    """

    while True:

        # 1. Reguläre Wartezeit bis zur nächsten vollen Stunde (+ 1 Minute)
        now = time.localtime()
        seconds_until_next = (60 - now.tm_min) * 60 - now.tm_sec + 60
        if seconds_until_next <= 0:
            seconds_until_next += 3600

        logger.info(f"Telegram: Nächster regulärer Versand in {seconds_until_next} Sekunden.")
        await asyncio.sleep(seconds_until_next)

        # 2. Regulärer Versand-Prozess
        if viewer.last_raw_image is None:
            continue

        try:
            img = viewer.get_current_image()

            # Wetterdaten aus dem viewer extrahieren
            # last_weather_formatted ist ein Dict, das wir in webcam_viewer.py befüllen
            w = viewer.last_weather_formatted or {}

            # Werte auslesen (mit Fallback '--' falls Daten fehlen)
            temp = w.get('temp', '--')
            wind = w.get('wind_speed') or w.get('wind', '--')

            # Caption zusammenbauen
            caption_text = f"🌡 Temperatur: {temp}°C\n💨 Wind: {wind} km/h"

            await send_telegram_photo(img, caption=caption_text)
        except Exception as e:
            logger.error(f"Telegram: Fehler beim regulären Overlay-Versand: {e}")

async def send_current_viewer_image(viewer):
    """Holt das aktuelle Bild aus dem Viewer und sendet es sofort."""
    if viewer.last_raw_image is None:
        logger.warning("Versand abgebrochen: Viewer hat noch kein Bild empfangen.")
        return

    try:
        # Kopie erstellen, um das Original-Frame nicht zu korrumpieren
        img = viewer.get_current_image()

        # Wetterdaten aus dem viewer extrahieren
        # last_weather_formatted ist ein Dict, das wir in webcam_viewer.py befüllen
        w = viewer.last_weather_formatted or {}

        # Werte auslesen (mit Fallback '--' falls Daten fehlen)
        temp = w.get('temp', '--')
        wind = w.get('wind_speed') or w.get('wind_speed_10m', '--')

        # Caption zusammenbauen
        caption_text = f"🌡 Temperatur: {temp}\n💨 Wind: {wind} km/h"

        await send_telegram_photo(img, caption=caption_text)

    except Exception as e:
        logger.error(f"Fehler beim manuellen Telegram-Versand: {e}")