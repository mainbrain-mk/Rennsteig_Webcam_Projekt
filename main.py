import signal
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from webcam_viewer import WebcamViewer
from database import init_db
from supervisor import supervisor
import telegram_sender  # Importiert für next_send und Funktionen
from telegram_sender import telegram_loop, telegram_enabled, send_current_viewer_image
import g15

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def main_async():
    init_db()

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    viewer = WebcamViewer()
    viewer.resize(1920, 1080)
    viewer.show()

    # --- DER PRÄZISE SHUTDOWN-HANDLER ---
    async def graceful_exit():
        """Stoppt die Loops und wartet bei Bedarf auf den Telegram-Slot."""
        logger.info("Shutdown-Sequenz eingeleitet...")

        # 1. Den regulären Telegram-Loop gezielt finden und stoppen
        for task in asyncio.all_tasks(loop):
            if task.get_name() == "Telegram_Task":
                task.cancel()
                logger.info("Regulärer Telegram-Loop wurde gestoppt.")

        # 2. Prüfen, ob wir im kritischen 2-Minuten-Fenster vor dem Slot sind
        # Wir nutzen die globale Variable next_send aus telegram_sender
        now = datetime.now()
        time_to_send = (telegram_sender.next_send - now).total_seconds()

        if 0 < time_to_send <= 120:
            logger.critical(f"RESTART-DELAY: Kritisches Fenster! Warte {int(time_to_send)}s auf Slot...")

            # Wir warten exakt bis zum berechneten Sendezeitpunkt
            await asyncio.sleep(max(0, time_to_send))

            # Jetzt das finale Bild mit aktuellem Overlay senden
            logger.info("Sende terminierten Slot-Snapshot vor Beenden...")
            success = await send_current_viewer_image(viewer)
            if success:
                logger.info("Telegram-Bestätigung erhalten.")
            else:
                logger.error("Telegram-Versand fehlgeschlagen oder Timeout.")

        # 3. Jetzt erst Qt beenden
        logger.info("Schließe Qt-Eventloop.")
        app.quit()

    def handle_signal():
        # Erstellt einen neuen Task für den sauberen Exit, ohne die Loop zu blockieren
        loop.create_task(graceful_exit())

    # SIGINT (Restart in PyCharm) und SIGTERM registrieren
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # Fallback für andere Umgebungen
            signal.signal(sig, lambda *args: handle_signal())

    async def setup_tasks():
        try:
            await asyncio.sleep(0.1)

            loop.run_in_executor(None, g15.g15_live_clock)
            logger.info("G15-Thread wurde gestartet.")

            loop.create_task(supervisor(viewer.update_webcam_loop, "Webcam"))
            loop.create_task(supervisor(viewer.update_weather_loop, "Wetter"))

            if telegram_enabled():
                # Task erstellen und Namen für die Identifizierung im graceful_exit vergeben
                t_task = loop.create_task(supervisor(telegram_loop, "Telegram", viewer))
                t_task.set_name("Telegram_Task")

            logger.info("Hintergrund-Tasks wurden in der QEventLoop registriert.")
        except Exception as e:
            logger.error(f"Fehler beim Task-Setup: {e}")

    loop.create_task(setup_tasks())

    try:
        loop.run_forever()
    except Exception as e:
        logger.error(f"Main Loop Fehler: {e}")
    finally:
        # Hier landet das Programm erst NACH app.quit() im graceful_exit
        g15.keep_running = False
        g15.shut_down()
        logger.info("Beende Hintergrund-Tasks...")

        # Alle noch laufenden Tasks (Webcam, Wetter etc.) canceln
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for task in pending:
            task.cancel()

        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        loop.stop()
        loop.close()
        logger.info("Programm sauber beendet.")
        sys.exit(0)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()