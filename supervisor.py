import asyncio
import logging

logger = logging.getLogger(__name__)

async def supervisor(coro_func, name, *args):
    """Startet eine async-Funktion und startet sie bei Absturz automatisch neu."""
    while True:
        try:
                await coro_func(*args)
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            # Dies wird jetzt beim Beenden der main.py getriggert
            logging.error(f"Supervisor '{name}' wurde sauber gestoppt.", exc_info=True)
            break
        except Exception as e:
            logging.error(f"Supervisor '{name}' Fehler: {e}")