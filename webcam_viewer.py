import asyncio
import logging
from datetime import datetime
from io import BytesIO
import aiohttp
import pytz
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import Qt, Slot, QRect
from PIL import Image
from astral import LocationInfo
from astral.sun import sun

from chart import show_chart

# Deine bestehenden Module
from config import (
    URL_WEBCAM, ORIG_W, ORIG_H,
    OVERLAY_ORIG_X, OVERLAY_ORIG_Y, OVERLAY_ORIG_W, OVERLAY_ORIG_H
)
from overlay import draw_overlay
from weather import WeatherService
from database import save_weather_to_db

logger = logging.getLogger(__name__)


class WebcamViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Webcam Rennsteigbahn")
        self.setStyleSheet("background-color: black;")

        # Layout ohne Ränder
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Das Bild-Label zur Anzeige
        self.label_image = QLabel()
        self.label_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.label_image)

        # Daten-Speicher
        self.last_raw_image = None
        self.last_weather_formatted = None
        self.weather_service = WeatherService()

        # Der transparente Button (RGBA: 0,0,0,0 für 100% Transparenz)
        self.logo_button = QPushButton(self)
        self.logo_button.setStyleSheet("background-color: rgba(0, 0, 0, 0); border: none;")
        self.logo_button.clicked.connect(self.on_logo_click)

        self.old_geometry = QRect(3840, 866, 1920, 1080)

    @Slot()
    def on_logo_click(self):
        """Wird ausgelöst, wenn auf das Wetter-Overlay geklickt wird."""
        logger.info("Öffne Wetter-Chart...")
        show_chart(self)

    def update_display(self):
        """Rendert das Overlay auf das Original und skaliert das Ergebnis."""
        if self.last_raw_image is None:
            return

        # 1. Overlay auf das Bild in voller Größe zeichnen
        try:
            from config import LAT, LON
            city = LocationInfo("Rennsteig", "Germany", "Europe/Berlin", LAT, LON)
            s = sun(city.observer, date=datetime.now(), tzinfo=pytz.timezone("Europe/Berlin"))

            # Zeiten zum Wetter-Dictionary hinzufügen
            w_data = self.last_weather_formatted.copy() if self.last_weather_formatted else {}
            w_data['sunrise'] = s['sunrise']
            w_data['sunset'] = s['sunset']
            w_data['noon'] = s['noon']
            w_data['now'] = datetime.now(pytz.timezone("Europe/Berlin"))
        except Exception as e:
            logger.error(f"Fehler bei Sonnenstandsberechnung: {e}")
            w_data = self.last_weather_formatted

        full_img = self.last_raw_image.copy()
        full_img = draw_overlay(full_img, w_data)

        # 2. PIL Image zu QPixmap konvertieren
        data = full_img.convert("RGBA").tobytes("raw", "RGBA")
        qimg = QImage(data, full_img.size[0], full_img.size[1], QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg)

        # 3. Skalieren unter Beibehaltung des Seitenverhältnisses
        scaled_pixmap = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.label_image.setPixmap(scaled_pixmap)

        # 4. Klick-Bereich des Buttons anpassen
        self.update_button_geometry(scaled_pixmap)

    def update_button_geometry(self, scaled_pixmap):
        """Berechnet die Button-Position basierend auf der aktuellen Skalierung."""
        scale = scaled_pixmap.width() / ORIG_W

        # Zentrierungs-Offsets des Labels berechnen
        offset_x = (self.width() - scaled_pixmap.width()) // 2
        offset_y = (self.height() - scaled_pixmap.height()) // 2

        bx = int(OVERLAY_ORIG_X * scale) + offset_x
        by = int(OVERLAY_ORIG_Y * scale) + offset_y
        bw = int(OVERLAY_ORIG_W * scale)
        bh = int(OVERLAY_ORIG_H * scale)

        self.logo_button.setGeometry(bx, by, bw, bh)

    def resizeEvent(self, event):
        """Wird von Qt bei jeder Fenstergrößenänderung aufgerufen."""
        self.update_display()
        super().resizeEvent(event)

    # --- Asynchrone Loops für den Supervisor in main.py ---

    async def update_webcam_loop(self):
        """Lädt das Webcam-Bild sofort beim Start und danach immer zur Sekunde :20."""
        logger.info("Webcam-Loop gestartet.")

        async def _download(session):
            try:
                async with session.get(URL_WEBCAM, timeout=15) as resp:
                    if resp.status == 200:
                        img_data = await resp.read()
                        self.last_raw_image = Image.open(BytesIO(img_data))
                        self.update_display()
                        logger.info(f"Webcam-Bild geladen um {datetime.now().strftime('%H:%M:%S')}")
                        return True
            except Exception as e:
                logger.error(f"Fehler beim Webcam-Download: {e}")
            return False

        async with aiohttp.ClientSession() as session:
            # 1. Sofortiger Versuch beim ersten Start
            await _download(session)

            # 2. Endlosschleife für die Synchronisation
            while True:
                now = datetime.now()
                target_second = 20

                # Berechnung der Wartezeit bis zur nächsten :20
                if now.second < target_second:
                    wait_seconds = target_second - now.second - (now.microsecond / 1_000_000.0)
                else:
                    wait_seconds = 60 - now.second + target_second - (now.microsecond / 1_000_000.0)

                # Warten bis zum nächsten Slot
                await asyncio.sleep(wait_seconds)

                # Bild ziehen
                await _download(session)

                # Verhindert Doppel-Trigger innerhalb derselben Sekunde
                await asyncio.sleep(1)

    async def update_weather_loop(self):
        """Holt Wetterdaten über den WeatherService, speichert sie und aktualisiert das UI."""
        logger.info("Wetter-Loop (Service-basiert) gestartet.")

        while True:
            try:
                # 1. Daten über die Klasse abrufen und intern verarbeiten
                success = await self.weather_service.update()

                if success:
                    # 2. In Datenbank speichern (Rohdaten liegen im Objekt)
                    try:
                        save_weather_to_db(self.weather_service.raw_data)
                        logger.debug("Wetterdaten erfolgreich in Datenbank gespeichert.")
                    except Exception as db_e:
                        logger.error(f"Fehler beim Speichern in die Datenbank: {db_e}")

                    # 3. Formatierte Daten für das UI übernehmen
                    self.last_weather_formatted = self.weather_service.formatted_data
                    self.update_display()  # UI-Refresh triggern

                    # 4. Wartezeit direkt vom Objekt berechnen lassen
                    wait_time = self.weather_service.compute_next_wait_seconds()
                    logger.info(f"Wetter aktualisiert. Nächster Check in {int(wait_time)}s.")

                else:
                    # Fehlerfall: Kurze Wartezeit vor Retry
                    wait_time = 30.0
                    logger.warning(f"Retry-Modus: Nächster Versuch in {wait_time} Sekunden...")

            except Exception as e:
                # Sicherheitsnetz für unerwartete Fehler
                logger.error(f"Unerwarteter Fehler in der Wetter-Schleife: {e}")
                wait_time = 60.0

            # 5. Schlafen bis zum nächsten Intervall
            await asyncio.sleep(wait_time)

    def get_current_image(self):
        """Schnittstelle für den Telegram-Sender."""
        if self.last_raw_image is None:
            return None
        try:
            from config import LAT, LON
            city = LocationInfo("Rennsteig", "Germany", "Europe/Berlin", LAT, LON)
            s = sun(city.observer, date=datetime.now(), tzinfo=pytz.timezone("Europe/Berlin"))

            # Zeiten zum Wetter-Dictionary hinzufügen
            w_data = self.last_weather_formatted.copy() if self.last_weather_formatted else {}
            w_data['sunrise'] = s['sunrise']
            w_data['sunset'] = s['sunset']
            w_data['noon'] = s['noon']
            w_data['now'] = datetime.now(pytz.timezone("Europe/Berlin"))
        except Exception as e:
            logger.error(f"Fehler bei Sonnenstandsberechnung: {e}")
            w_data = self.last_weather_formatted

        return draw_overlay(self.last_raw_image.copy(), w_data)

    def closeEvent(self, event):
        """Wird aufgerufen, wenn der Benutzer das Fenster schließt."""
        logger.info("Fenster wurde vom Benutzer geschlossen. Programm wird beendet...")
        # Hier könntest du ggf. noch Aufräumarbeiten erledigen
        event.accept()

    def keyPressEvent(self, event):
        """Behandelt Tastatureingaben für den Vollbildmodus."""
        # Strg + F Trigger
        if event.key() == Qt.Key.Key_F and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if self.isFullScreen():
                self.showNormal()
                if self.old_geometry:
                    self.setGeometry(self.old_geometry)  # Alte Größe wiederherstellen
                logger.info("Vollbildmodus beendet, ursprüngliche Größe wiederhergestellt.")
            else:
                self.old_geometry = self.geometry()  # Aktuelle Größe merken
                print(self.old_geometry)
                self.showFullScreen()
                logger.info("Vollbildmodus aktiviert.")

        # Esc beendet den Vollbildmodus ebenfalls
        elif event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
            if self.old_geometry:
                self.setGeometry(self.old_geometry)

        super().keyPressEvent(event)