import logging
import traceback
from datetime import datetime, timedelta

import pytz
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QDateTime, QMargins, QRectF
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QDateTimeAxis, QValueAxis, QScatterSeries
from PySide6.QtGui import QPainter, QColor, QPen, QImage, QPainterPath, QBrush, QLinearGradient, QGradient, QFont

from database import load_last_7_days

logger = logging.getLogger(__name__)


class ChartDialog(QDialog):
    def __init__(self, parent=None, live_mode=False):
        super().__init__(parent)
        self.setWindowTitle("Wetterverlauf Rennsteigbahn")
        self.live_mode = live_mode

        layout = QVBoxLayout(self)

        rows = load_last_7_days()
        if not rows:
            layout.addWidget(QLabel("Keine Daten gefunden."))
            return

        # 1. Chart Setup
        self.chart = QChart()
        self.chart.setTheme(QChart.ChartTheme.ChartThemeDark)

        # Den Chart-Hintergrund für die PlotArea aktivieren
        self.chart.setPlotAreaBackgroundVisible(True)

        self.darker = 190
        self.update_chart_background()

        # Den äußeren Hintergrund des Chart-Widgets transparent lassen
        #self.chart.setPlotAreaBackgroundVisible(False)
        #self.chart.setBackgroundVisible(True)

        # Titel-Farbe auf Weiß (damit man ihn auf dem Blau sieht)
        font = QFont()
        font.setPointSize(18)  # Hier die gewünschte Größe in Punkt (pt)
        font.setBold(True)  # Optional: Fett drucken
        #font.setFamily("Arial")  # Optional: Schriftart festlegen

        self.chart.setTitle("Wetterdaten der letzten 7 Tage")
        self.chart.setTitleFont(font)
        self.chart.setTitleBrush(QBrush(QColor("white")))

        self.chart.setMargins(QMargins(15, 10, 15, 60))
        self.chart.layout().setContentsMargins(0, 0, 0, 0)

        self.view = QChartView(self.chart)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self.view)

        # 2. Achsen Setup
        self.axis_x = QDateTimeAxis()
        self.axis_x.setFormat("dd.MM. HH:mm")
        self.axis_x.setLabelsAngle(-75)
        # Vertikale Gitterlinien dezent gepunktet
        x_grid = QPen(QColor(60, 60, 70))
        x_grid.setStyle(Qt.PenStyle.DotLine)
        self.axis_x.setGridLinePen(x_grid)

        self.axis_y_temp = QValueAxis()
        self.axis_y_temp.setTitleText("Temperatur [°C]")
        self.axis_y_temp.setGridLineVisible(False)  # Wir zeichnen das Gitter manuell!

        self.axis_y_wind = QValueAxis()
        self.axis_y_wind.setTitleText("Wind [km/h]")
        self.axis_y_wind.setGridLineVisible(False)

        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.axis_y_temp, Qt.AlignmentFlag.AlignLeft)
        self.chart.addAxis(self.axis_y_wind, Qt.AlignmentFlag.AlignRight)

        # 3. Series initialisieren
        self.temp_series = QLineSeries()
        self.temp_series.setName("Temperatur (°C)")
        self.temp_series.setPen(QPen(QColor("#0078d4"), 3))

        self.feels_series = QLineSeries()
        self.feels_series.setName("Gefühlt (°C)")
        self.feels_series.setPen(QPen(QColor("#4fc3f7"), 1, Qt.PenStyle.DashLine))

        self.wind_series = QLineSeries()
        self.wind_series.setName("Wind (km/h)")
        self.wind_series.setPen(QPen(QColor("#228b22"), 2, Qt.PenStyle.DashDotLine))

        directions = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"]
        self.dir_series_map = {d: QScatterSeries() for d in directions}
        self._setup_wind_icons(directions)

        # 4. Daten verarbeiten
        t_data = []
        last_marked_slot = None
        berlin_tz = pytz.timezone('Europe/Berlin')

        for r in rows:
            try:
                dt = datetime.fromisoformat(r[0])
                dt_local = dt.astimezone(berlin_tz)

                ts = float(dt.timestamp() * 1000)
                t, w = float(r[1]), float(r[2])

                self.temp_series.append(ts, t)
                self.wind_series.append(ts, w)
                t_data.append(t)

                if len(r) > 3 and r[3] is not None:
                    f = float(r[3])
                    self.feels_series.append(ts, f)
                    t_data.append(f)

                if (dt.hour + 1) % 4 == 0:

                    # Eindeutiger Identifikator für diesen 4-Stunden-Block
                    current_slot = f"{dt.day}_{dt.hour}"

                    # 3. Wenn dieser Block noch keinen Pfeil hat UND Daten da sind:
                    if current_slot != last_marked_slot and len(r) > 4 and r[4] is not None:
                        try:
                            wind_dir = float(r[4])
                            idx = int((wind_dir + 22.5) / 45) % 8

                            # Marker zeichnen
                            self.dir_series_map[directions[idx]].append(ts, w)

                            # Slot als "erledigt" markieren
                            last_marked_slot = current_slot
                            logger.debug(f"Windpfeil nachgeholt um {dt.hour}:{dt.minute}")
                        except ValueError:
                            continue  # Falls r[4] keine Zahl ist

            except:
                traceback.print_exc()
                continue

        # 5. Series binden
        for s in [self.temp_series, self.feels_series]:
            self.chart.addSeries(s)
            s.attachAxis(self.axis_x)
            s.attachAxis(self.axis_y_temp)

        self.chart.addSeries(self.wind_series)
        self.wind_series.attachAxis(self.axis_x)
        self.wind_series.attachAxis(self.axis_y_wind)

        for s in self.dir_series_map.values():
            self.chart.addSeries(s)
            s.attachAxis(self.axis_x)
            s.attachAxis(self.axis_y_wind)
            m = self.chart.legend().markers(s)
            if m: m[0].setVisible(False)

        # 6. Skalierung & Manuelles Farb-Gitter
        if t_data:
            local_tz = pytz.timezone("Europe/Berlin")

            # 1. Ersten/Letzten Zeitpunkt als echte UTC-Objekte markieren
            first_utc = datetime.fromisoformat(rows[0][0]).replace(tzinfo=pytz.UTC)
            last_utc = datetime.fromisoformat(rows[-1][0]).replace(tzinfo=pytz.UTC)

            # 2. In Lokalzeit umwandeln, um die "Wandzeit" zu bestimmen
            first_local = first_utc.astimezone(local_tz)

            # 3. Den Startpunkt auf die nächste lokale 8h-Marke abrunden (00, 08, 16 Uhr)
            # Das sorgt dafür, dass die Ticks im Chart "schön" aussehen (z.B. 08:00 statt 07:00)
            start_local = first_local.replace(hour=(first_local.hour // 8) * 8,
                                              minute=0, second=0, microsecond=0)

            # 4. Zurück nach UTC wandeln für die interne Chart-Logik
            # So bleibt die X-Achse physikalisch linear (keine Sprünge bei Zeitumstellung)
            start_utc = start_local.astimezone(pytz.UTC)

            # 5. Anzahl der Intervalle basierend auf der echten Zeitdifferenz berechnen
            diff_seconds = (last_utc - start_utc).total_seconds()
            num_intervals = int(diff_seconds // 28800) + 1
            end_utc = start_utc + timedelta(hours=num_intervals * 8)

            # 6. QDateTime für Qt Charts erstellen (Wichtig: Qt.UTC angeben)
            qt_start = QDateTime.fromMSecsSinceEpoch(int(start_utc.timestamp() * 1000), Qt.TimeSpec.UTC)
            qt_end = QDateTime.fromMSecsSinceEpoch(int(end_utc.timestamp() * 1000), Qt.TimeSpec.UTC)

            ts_start = float(qt_start.toMSecsSinceEpoch())
            ts_end = float(qt_end.toMSecsSinceEpoch())

            self.axis_x.setTickCount(num_intervals + 1)
            self.axis_x.setRange(qt_start, qt_end)

            # --- Skalierung Y-Achse (bleibt gleich) ---
            y_min = (int(min(t_data)) // 2) * 2 - 2
            y_max = (int(max(t_data)) // 2) * 2 + 2
            y_ticks = int((y_max - y_min) / 2) + 1
            self.axis_y_temp.setRange(y_min, y_max)
            self.axis_y_temp.setTickCount(y_ticks)

            wind_values = [float(r[2]) for r in rows if r[2] is not None]
            max_wind = max(wind_values) if wind_values else 20
            wind_limit = (int(max_wind) // 2 + 1) * 2

            self.axis_y_wind.setRange(0, wind_limit)
            self.axis_y_wind.setTickCount(y_ticks)

            # --- DAS MANUELLE FARB-GITTER ---
            green_col = QColor(40, 80, 40, 150)
            blue_col = QColor(40, 60, 100, 150)
            for val in range(y_min, y_max + 1, 2):
                grid_line = QLineSeries()
                # Farblogik wie zuvor...
                if val == 0:
                    pen = QPen(QColor("#4fc3f7"), 1, Qt.PenStyle.DashLine)
                elif val > 0:
                    green_val = min(255, 80 + (val * 5))
                    green_col = QColor(40, green_val, 40, 180)
                    pen = QPen(green_col, 1, Qt.PenStyle.DotLine)
                else:
                    blue_val = min(255, 100 + (abs(val) * 10))
                    blue_col = QColor(40, 60, blue_val, 180)
                    pen = QPen(blue_col, 1, Qt.PenStyle.DotLine)

                grid_line.setPen(pen)
                grid_line.append(ts_start, val)
                grid_line.append(ts_end, val)
                self.chart.addSeries(grid_line)
                grid_line.attachAxis(self.axis_x)
                grid_line.attachAxis(self.axis_y_temp)

                m = self.chart.legend().markers(grid_line)
                if m: m[0].setVisible(False)

            logger.debug(f"green_col: {green_col}, blue_col: {blue_col}")

        self.update_ui_mode()


    def update_ui_mode(self):
        """Passt die UI-Elemente dynamisch an den Live-Modus an oder ab."""
        has_axes = hasattr(self, 'axis_x') and hasattr(self, 'axis_y_temp') and hasattr(self, 'axis_y_wind')
        if self.live_mode:
            # Deine gewünschte Export-Größe
            width, height = 720, 320
            self.resize(width, height)

            self.chart.setBackgroundVisible(False)
            self.chart.setPlotAreaBackgroundVisible(False)

            # 1. Das Layout-Management von Qt Charts minimieren
            self.chart.layout().setContentsMargins(0, 0, 0, 0)

            # 2. Die Margins des Charts auf 0 setzen.
            # Falls die Linien immer noch zu klein sind, kann man hier
            # sogar negative Werte probieren (z.B. -10), um den Weißraum zu killen.
            self.chart.setMargins(QMargins(0, 0, 0, 0))

            # 3. Den Bereich, in dem gezeichnet wird, maximieren
            # Wir lassen oben nur 20px Platz für die Legende
            self.chart.setPlotArea(QRectF(0, 40, width, height-40))

            if self.chart.legend():
                self.chart.legend().show()

                # 1. WICHTIG: Horizontal ausrichten statt untereinander
                self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
                self.chart.legend().layout().setContentsMargins(10, 0, 10, 0)

                # 2. Die Box für die Legende über die fast volle Breite ziehen (z.B. 700px)
                # Damit haben beide Labels (Temperatur & Wind) nebeneinander Platz
                self.chart.legend().setGeometry(QRectF(0, 5, width, 30))

                # Schrift-Setup (Weiß und Fett)
                font = self.chart.legend().font()
                font.setPointSize(10)
                font.setBold(True)
                self.chart.legend().setFont(font)
                self.chart.legend().setLabelColor(QColor("white"))

            self.chart.setTitle("")

            if has_axes:
                self.axis_x.setLabelsVisible(False)
                self.axis_y_temp.setLabelsVisible(False)
                self.axis_y_wind.setLabelsVisible(False)
                # Titel entfernen
                self.axis_x.setTitleText("")
                self.axis_y_temp.setTitleText("")
                self.axis_y_wind.setTitleText("")
        else:
            # 1. Zurück zur Standardgröße
            width, height = 1280, 720
            self.resize(width, height)

            # 2. WICHTIG: Manuelle PlotArea löschen!
            # Damit darf Qt das Diagramm wieder automatisch im Fenster verteilen.
            self.chart.setPlotArea(QRectF())  # Übergabe eines leeren QRectF setzt es zurück

            # 3. Margins zurück auf Standard
            self.chart.setMargins(QMargins(15, 10, 15, 60))

            # 4. Hintergrund und Theme wiederherstellen
            self.chart.setTheme(QChart.ChartTheme.ChartThemeDark)
            self.chart.setBackgroundVisible(True)
            self.update_chart_background()

            # 5. Legende und Titel wieder normal positionieren
            if self.chart.legend():
                self.chart.legend().show()
                #self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)  # Legende wieder nach unten
                # Geometrie auf 0 setzen, damit das automatische Layout übernimmt
                self.chart.legend().setGeometry(QRectF())

            self.chart.setTitle("Wetterdaten der letzten 7 Tage")

            # Achsen wieder beschriften
            if has_axes:
                self.axis_x.setLabelsVisible(True)
                self.axis_y_temp.setLabelsVisible(True)
                self.axis_y_wind.setLabelsVisible(True)
                self.axis_y_wind.setLineVisible(True)
                self.axis_y_temp.setTitleText("Temperatur [°C]")
                self.axis_y_wind.setTitleText("Wind [km/h]")

        # WICHTIG: Chart anweisen, sich neu zu zeichnen
        self.chart.update()

    def update_chart_background(self, color_top=QColor(40, 80, 40, 150), color_bottom=QColor(40, 60, 100, 150)):
        # Neuen Gradienten erstellen
        gradient = QLinearGradient(0, 0, 0, 1)
        gradient.setCoordinateMode(QGradient.CoordinateMode.ObjectBoundingMode)
        gradient.setColorAt(0.0, color_top.darker(self.darker))
        gradient.setColorAt(0.5, QColor(0, 0, 0))
        gradient.setColorAt(1.0, color_bottom.darker(self.darker))

        # Dem Chart zuweisen – das löst automatisch ein neu zeichnen (Repaint) aus
        self.chart.setBackgroundBrush(gradient)

    def _setup_wind_icons(self, directions):
        path = QPainterPath()
        path.moveTo(0, 8)
        path.lineTo(-4, -4)
        path.lineTo(0, -2)
        path.lineTo(4, -4)
        path.closeSubpath()
        for i, d in enumerate(directions):
            img = QImage(20, 20, QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.translate(10, 10)
            p.rotate(i * 45)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#228b22").lighter(150))
            p.drawPath(path)
            p.end()
            self.dir_series_map[d].setBrush(QBrush(img))
            self.dir_series_map[d].setMarkerShape(QScatterSeries.MarkerShape.MarkerShapeRectangle)
            self.dir_series_map[d].setMarkerSize(20)
            self.dir_series_map[d].setBorderColor(Qt.GlobalColor.transparent)

    def chart_image(self):
        # WICHTIG: Das Chart braucht eine Viewport-Größe, um sich zu berechnen
        size = self.size()

        # Erstelle eine temporäre ChartView, falls keine existiert
        # oder nutze die vorhandene, um das Layout zu erzwingen
        view = QChartView(self.chart)
        view.setMinimumSize(size)
        view.resize(size)

        # Das hier erzwingt, dass Qt die Achsen und Abstände berechnet
        self.chart.layout().invalidate()
        self.chart.layout().activate()

        image = QImage(size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Jetzt das Chart direkt in den Painter rendern
        self.chart.scene().render(painter)
        painter.end()

        return image

    def close_window(self):
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_L:
            self.live_mode = not self.live_mode
            logger.info(f"Schalte Chart-Modus um: {'LIVE' if self.live_mode else 'NORMAL'}")
            self.update_ui_mode()

        # Screenshot-Funktion mit Strg+S
        if event.key() == Qt.Key.Key_S and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):

            image = self.chart_image()

            # Speichern des Bildes
            filename = f"wetter_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            if image.save(filename):
                logger.info(f"Chart erfolgreich gespeichert: {filename}")

            else:
                logger.error("Fehler beim Speichern des Charts.")

        elif event.key() == Qt.Key.Key_Escape:
            logger.debug("Chart-Fenster per Esc geschlossen.")
            self.close_window()

        # Plus-Taste auf dem Nummernblock
        elif event.key() == Qt.Key.Key_Plus:

            self.darker -= 1
            self.update_chart_background()
            logger.debug(f"NumPad Plus gedrückt: darker={self.darker}")

        # Minus-Taste auf dem Nummernblock
        elif event.key() == Qt.Key.Key_Minus:
            self.darker += 1
            self.update_chart_background()
            logger.debug(f"NumPad Minus gedrückt: darker={self.darker}")
        else:
            super().keyPressEvent(event)

def show_chart(parent_widget):
    dialog = ChartDialog(parent_widget)
    dialog.setStyleSheet("QDialog { background-color: #000000; }")
    dialog.exec()


def export_live_chart_rgba():
    try:
        # 1. Dialog im Live-Modus erstellen
        dialog = ChartDialog(live_mode=True)
        dialog.update_ui_mode()

        # Zielgröße definieren
        width, height = 720, 320

        # --- DER ENTSCHEIDENDE FIX ---
        # Wir zwingen das Chart-Objekt auf die volle Größe der Scene
        dialog.chart.resize(width, height)
        # Wir setzen das Layout-Handling außer Kraft und geben feste Maße vor
        dialog.chart.setGeometry(0, 0, width, height)
        # ------------------------------

        # Headless-Berechnung (Schocktherapie)
        dialog.setWindowOpacity(0.0)
        dialog.show()
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        # QImage in Zielgröße erstellen
        q_img = QImage(width, height, QImage.Format.Format_ARGB32)
        q_img.fill(Qt.GlobalColor.transparent)

        painter = QPainter(q_img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Wir rendern nun die Scene.
        # Da das Chart nun 400x160 groß ist, füllt es das QImage aus.
        dialog.chart.scene().render(painter)
        painter.end()

        dialog.close()

        # Konvertierung zu PIL (unverändert)
        q_img = q_img.convertToFormat(QImage.Format.Format_RGBA8888)
        from PIL import Image
        pil_img = Image.frombuffer(
            "RGBA", (q_img.width(), q_img.height()),
            q_img.bits().tobytes(), "raw", "RGBA", 0, 1
        )
        return pil_img.copy()

    except Exception as e:
        logger.error(f"Fehler im Chart-Export: {e}")
        return None