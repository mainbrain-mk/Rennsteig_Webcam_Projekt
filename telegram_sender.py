import asyncio
import logging
from datetime import datetime, timedelta
from io import BytesIO

from telegram import Bot
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

next_send = datetime.now()
bot = None

def telegram_enabled():
    """Prüft, ob Telegram korrekt konfiguriert ist."""
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

def start_bot():
    global bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

async def send_telegram_photo(img_pil, caption=""):
    """Sendet ein PIL-Bild direkt an Telegram."""
    if not telegram_enabled():
        logger.warning("Telegram nicht konfiguriert – kein Versand.")
        return False

    if not bot:
        start_bot()

    bio = BytesIO()
    img_pil.save(bio, format="JPEG")
    bio.seek(0)

    try:
        pic_send = await bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=bio,
            caption=caption
        )
        if pic_send and pic_send.message_id:
            logger.debug(f"Telegram-Bild erfolgreich gesendet (ID: {pic_send.message_id})")
            return True
    except Exception as e:
        logger.error(f"Telegram-Versand fehlgeschlagen: {e}")

    return False

async def telegram_loop(viewer):
    global next_send
    """
    sendet ein bild in Minute 01, 16, 31, 46
    """
    if not telegram_enabled():
        logger.info("Telegram deaktiviert – Loop wird nicht gestartet.")
        return

    while True:
        try:
            now = datetime.now()

            minutes_to_next_quarter = 15 - (now.minute % 15)
            wait_seconds = ((minutes_to_next_quarter + 1) * 60) - now.second

            if wait_seconds <= 0:
                wait_seconds = 15 * 60

            next_send = now + timedelta(seconds=wait_seconds)

            logger.info(f"Nächster Telegram-Versand in {wait_seconds // 60} Min {wait_seconds % 60} Sek.")

            await asyncio.sleep(wait_seconds)

            # Bild senden
            send = await send_current_viewer_image(viewer)
            if not send:
                await asyncio.sleep(60)
                await send_current_viewer_image(viewer)

        except asyncio.CancelledError:
            # Wichtig: re-raisen statt nur zu loggen+breaken! Ein "break" hier lässt
            # telegram_loop() normal zurückkehren, statt die Cancellation nach oben
            # durchzureichen - der supervisor() in supervisor.py sieht das dann als
            # regulären Abschluss an und startet telegram_loop() (mit frischem,
            # nicht mehr abgebrochenem State) direkt wieder neu. Der ursprüngliche
            # task.cancel()-Aufruf verpufft dadurch wirkungslos, und main.py hängt
            # beim Beenden für immer in run_until_complete(), weil dieser Task nie fertig wird.
            logger.info("Telegram-Loop wurde sauber beendet.")
            raise
        except Exception as e:
            logger.error(f"Fehler in der Telegram-Loop: {e}")
            await asyncio.sleep(60)

async def send_current_viewer_image(viewer):
    """Holt das aktuelle Bild aus dem Viewer und sendet es sofort."""
    if viewer.actual_raw_image is None:
        logger.warning("Versand abgebrochen: Viewer hat noch kein Bild empfangen.")
        return False

    try:
        img = viewer.get_current_image()
        w = viewer.last_weather_formatted or {}

        temp = w.get('temp', '--')
        wind = w.get('wind', '--')

        caption_text = f"🌡 Temperatur: {temp}\n💨 {wind}"

        return await send_telegram_photo(img, caption=caption_text)

    except Exception as e:
        logger.error(f"Fehler beim Telegram-Versand: {e}")
        return False
