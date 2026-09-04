import signal
import sys
import asyncio
import logging
from datetime import datetime
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from webcam_viewer import WebcamViewer
from database import init_db
from supervisor import supervisor
import telegram_sender
from telegram_sender import telegram_loop, telegram_enabled, send_current_viewer_image
import g15

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def graceful_exit(app, loop, viewer):
    """Stoppt die Loops und wartet bei Bedarf auf den Telegram-Slot."""
    logger.info("Shutdown-Sequenz eingeleitet...")

    # 1. Den regulären Telegram-Loop gezielt finden und stoppen
    for task in asyncio.all_tasks(loop):
        if task.get_name() == "Telegram_Task":
            task.cancel()
            logger.info("Regulärer Telegram-Loop wurde gestoppt.")

    # 2. Prüfen, ob wir im kritischen 2-Minuten-Fenster vor dem Slot sind
    # (nur relevant, wenn Telegram überhaupt aktiv ist - sonst wurde next_send
    # nie aktualisiert und enthält noch den Wert vom Programmstart)
    if telegram_enabled():
        now = datetime.now()
        time_to_send = (telegram_sender.next_send - now).total_seconds()

        if 0 < time_to_send <= 120:
            logger.critical(f"RESTART-DELAY: Kritisches Fenster! Warte {int(time_to_send)}s auf Slot...")
            await asyncio.sleep(max(0, time_to_send))

            logger.info("Sende terminierten Slot-Snapshot vor Beenden...")
            success = await send_current_viewer_image(viewer)
            if success:
                logger.info("Telegram-Bestätigung erhalten.")
            else:
                logger.error("Telegram-Versand fehlgeschlagen oder Timeout.")

    # 3. Qt beenden
    logger.info("Schließe Qt-Eventloop.")
    app.quit()


async def setup_tasks(loop, viewer):
    try:
        await asyncio.sleep(0.1)

        loop.create_task(supervisor(g15.run_g15, "G15", loop))
        logger.info("G15-Task (supervised) wurde gestartet.")

        loop.create_task(supervisor(g15.update_secondary_weather_loop, "G15-Wetter"))

        loop.create_task(supervisor(viewer.update_webcam_loop, "Webcam"))
        loop.create_task(supervisor(viewer.update_weather_loop, "Wetter"))

        if telegram_enabled():
            t_task = loop.create_task(supervisor(telegram_loop, "Telegram", viewer))
            t_task.set_name("Telegram_Task")

        logger.info("Hintergrund-Tasks wurden in der QEventLoop registriert.")
    except Exception as e:
        logger.error(f"Fehler beim Task-Setup: {e}")


def main():
    init_db()

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    viewer = WebcamViewer()
    viewer.resize(1920, 1080)
    viewer.show()

    shutdown_started = False

    def handle_signal():
        nonlocal shutdown_started
        if shutdown_started:
            logger.warning("Shutdown läuft bereits, weiteres Signal ignoriert.")
            return
        shutdown_started = True
        loop.create_task(graceful_exit(app, loop, viewer))

    # SIGINT (Restart in PyCharm) und SIGTERM registrieren
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda *args: handle_signal())

    loop.create_task(setup_tasks(loop, viewer))

    try:
        # Kein "with loop:" hier: qasync's QEventLoop.__exit__() ruft close() auf,
        # was self.__app auf None setzt. Der finally-Block unten braucht die Loop
        # aber noch (run_until_complete für die Task-Cancellation) - mit "with"
        # crasht das mit "AttributeError: 'NoneType' object has no attribute 'exec_'".
        # loop.close() wird stattdessen explizit unten am Ende des finally-Blocks aufgerufen.
        loop.run_forever()
    except Exception as e:
        logger.error(f"Main Loop Fehler: {e}")
    finally:
        g15.keep_running = False
        g15.shut_down()
        logger.info("Beende Hintergrund-Tasks...")

        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for task in pending:
            task.cancel()

        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        loop.close()
        logger.info("Programm sauber beendet.")
        sys.exit(0)


if __name__ == "__main__":
    main()
