import sys
import asyncio
import logging
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from webcam_viewer import WebcamViewer
from database import init_db
from supervisor import supervisor
from telegram_sender import telegram_loop, telegram_enabled

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main_async():
    init_db()

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    viewer = WebcamViewer()
    viewer.resize(1920, 1080)
    viewer.show()

    async def setup_tasks():
        try:
            await asyncio.sleep(0.1)
            # Wir speichern die Tasks nicht einzeln, da wir sie später über asyncio.all_tasks() finden
            loop.create_task(supervisor(viewer.update_webcam_loop, "Webcam"))
            loop.create_task(supervisor(viewer.update_weather_loop, "Wetter"))

            if telegram_enabled():
                loop.create_task(supervisor(telegram_loop, "Telegram", viewer))

            logger.info("Hintergrund-Tasks wurden in der QEventLoop registriert.")
        except Exception as e:
            logger.error(f"Fehler beim Task-Setup: {e}")

    loop.create_task(setup_tasks())

    try:
        # Wir lassen die Loop laufen, bis die Qt-App beendet wird
        loop.run_forever()
    except Exception as e:
        logger.error(f"Main Loop Fehler: {e}")
    finally:
        logger.info("Beende Hintergrund-Tasks...")

        # 1. Alle laufenden Tasks sammeln
        pending = asyncio.all_tasks(loop)

        # 2. Tasks abbrechen
        for task in pending:
            task.cancel()

        # 3. Den Tasks Zeit geben, auf den Cancel zu reagieren
        # Wir nutzen run_until_complete, um sauber aufzuräumen
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        # 4. Loop stoppen und schließen
        loop.stop()
        loop.close()

        logger.info("Alle Tasks wurden beendet. Programm wird geschlossen.")

        # 5. Explizites Beenden, um SIGABRT zu vermeiden
        sys.exit(0)

def main():
    # Wir starten main_async direkt als Coroutine
    asyncio.run(main_async())


if __name__ == "__main__":
    main()