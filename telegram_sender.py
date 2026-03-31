# telegram_sender.py

import asyncio
import logging
from datetime import datetime
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
        logger.debug("Telegram-Bild erfolgreich gesendet.")
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

    try:
        # Aktuelle Zeit holen
        now = datetime.now()

        # Berechne die Minuten bis zum nächsten 15er Intervall
        # Beispiel: 12:04 -> nächstes ist 12:15 (11 Min warten)
        # Beispiel: 12:55 -> nächstes ist 13:00 (5 Min warten)
        minutes_to_next_quarter = 15 - (now.minute % 15)

        # Zielzeit: Jetzt + Differenz, Sekunden auf 0, plus 5 Sek Puffer
        # Der Puffer sorgt dafür, dass wir sicher im neuen Intervall landen
        wait_seconds = ((minutes_to_next_quarter + 1) * 60) - now.second

        if wait_seconds <= 0:  # Falls wir extrem nah dran sind
            wait_seconds = 15 * 60

        logger.info(f"Nächster Telegram-Versand in {wait_seconds // 60} Min {wait_seconds % 60} Sek.")

        await asyncio.sleep(wait_seconds)

        # Bild senden
        await send_current_viewer_image(viewer)

    except Exception as e:
        logger.error(f"Fehler in der Telegram-Loop: {e}")
        await asyncio.sleep(60)  # Bei Fehler eine Minute warten und neu versuchen

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
        wind = w.get('wind', '--')

        # Caption zusammenbauen
        caption_text = f"🌡 Temperatur: {temp}\n💨 {wind}"

        await send_telegram_photo(img, caption=caption_text)

    except Exception as e:
        logger.error(f"Fehler beim manuellen Telegram-Versand: {e}")