import logging
import traceback
from datetime import datetime, timedelta

import pytz
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QDateTime, QMargins, QTimeZone
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QDateTimeAxis, QValueAxis, QScatterSeries
from PySide6.QtGui import QPainter, QColor, QPen, QImage, QPainterPath, QBrush, QLinearGradient, QGradient

from database import load_last_7_days

logger = logging.getLogger(__name__)


class ChartDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wetterverlauf Rennsteigbahn")
        self.resize(1280, 720)
        layout = QVBoxLayout(self)

        rows = load_last_7_days()
        if not rows:
            layout.addWidget(QLabel("Keine Daten gefunden."))
            return

        # 1. Chart Setup
        self.chart = QChart()
        self.chart.setTheme(QChart.ChartThemeDark)

        # Den Chart-Hintergrund für die PlotArea aktivieren
        self.chart.setPlotAreaBackgroundVisible(True)

        self.darker = 190
        self.update_chart_background()

        # Den äußeren Hintergrund des Chart-Widgets transparent lassen
        self.chart.setPlotAreaBackgroundVisible(False)
        self.chart.setBackgroundVisible(True)

        # Titel-Farbe auf Weiß (damit man ihn auf dem Blau sieht)
        self.chart.setTitleBrush(QBrush(QColor("white")))

        self.chart.setTitle("Wetterdaten der letzten 7 Tage")

        self.chart.setMargins(QMargins(15, 10, 15, 60))
        self.chart.layout().setContentsMargins(0, 0, 0, 0)

        self.view = QChartView(self.chart)
        self.view.setRenderHint(QPainter.Antialiasing)
        layout.addWidget(self.view)

        # 2. Achsen Setup
        self.axis_x = QDateTimeAxis()
        self.axis_x.setFormat("dd.MM. HH:mm")
        self.axis_x.setLabelsAngle(-75)
        # Vertikale Gitterlinien dezent gepunktet
        x_grid = QPen(QColor(60, 60, 70))
        x_grid.setStyle(Qt.DotLine)
        self.axis_x.setGridLinePen(x_grid)

        self.axis_y_temp = QValueAxis()
        self.axis_y_temp.setTitleText("Temperatur [°C]")
        self.axis_y_temp.setGridLineVisible(False)  # Wir zeichnen das Gitter manuell!

        self.axis_y_wind = QValueAxis()
        self.axis_y_wind.setTitleText("Wind [km/h]")
        self.axis_y_wind.setGridLineVisible(False)

        self.chart.addAxis(self.axis_x, Qt.AlignBottom)
        self.chart.addAxis(self.axis_y_temp, Qt.AlignLeft)
        self.chart.addAxis(self.axis_y_wind, Qt.AlignRight)

        # 3. Series initialisieren
        self.temp_series = QLineSeries()
        self.temp_series.setName("Temperatur (°C)")
        self.temp_series.setPen(QPen(QColor("#0078d4"), 3))

        self.feels_series = QLineSeries()
        self.feels_series.setName("Gefühlt (°C)")
        self.feels_series.setPen(QPen(QColor("#4fc3f7"), 1, Qt.DashLine))

        self.wind_series = QLineSeries()
        self.wind_series.setName("Wind (km/h)")
        self.wind_series.setPen(QPen(QColor("#228b22"), 2, Qt.DashDotLine))

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
            s.attachAxis(self.axis_x);
            s.attachAxis(self.axis_y_temp)

        self.chart.addSeries(self.wind_series)
        self.wind_series.attachAxis(self.axis_x);
        self.wind_series.attachAxis(self.axis_y_wind)

        for s in self.dir_series_map.values():
            self.chart.addSeries(s)
            s.attachAxis(self.axis_x);
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
            qt_start = QDateTime.fromMSecsSinceEpoch(int(start_utc.timestamp() * 1000), Qt.UTC)
            qt_end = QDateTime.fromMSecsSinceEpoch(int(end_utc.timestamp() * 1000), Qt.UTC)

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
                    pen = QPen(QColor("#4fc3f7"), 1, Qt.DashLine)
                elif val > 0:
                    green_val = min(255, 80 + (val * 5))
                    green_col = QColor(40, green_val, 40, 180)
                    pen = QPen(green_col, 1, Qt.DotLine)
                else:
                    blue_val = min(255, 100 + (abs(val) * 10))
                    blue_col = QColor(40, 60, blue_val, 180)
                    pen = QPen(blue_col, 1, Qt.DotLine)

                grid_line.setPen(pen)
                grid_line.append(ts_start, val)
                grid_line.append(ts_end, val)
                self.chart.addSeries(grid_line)
                grid_line.attachAxis(self.axis_x)
                grid_line.attachAxis(self.axis_y_temp)

                m = self.chart.legend().markers(grid_line)
                if m: m[0].setVisible(False)

            logger.debug(f"green_col: {green_col}, blue_col: {blue_col}")

    def update_chart_background(self, color_top=QColor(40, 80, 40, 150), color_bottom=QColor(40, 60, 100, 150)):
        # Neuen Gradienten erstellen
        gradient = QLinearGradient(0, 0, 0, 1)
        gradient.setCoordinateMode(QGradient.ObjectBoundingMode)
        gradient.setColorAt(0.0, color_top.darker(self.darker))
        gradient.setColorAt(0.5, QColor(0, 0, 0))
        gradient.setColorAt(1.0, color_bottom.darker(self.darker))

        # Dem Chart zuweisen – das löst automatisch ein Neuzeichnen (Repaint) aus
        self.chart.setBackgroundBrush(gradient)

    def _setup_wind_icons(self, directions):
        path = QPainterPath()
        path.moveTo(0, 8);
        path.lineTo(-4, -4);
        path.lineTo(0, -2);
        path.lineTo(4, -4);
        path.closeSubpath()
        for i, d in enumerate(directions):
            img = QImage(20, 20, QImage.Format_ARGB32);
            img.fill(Qt.transparent)
            p = QPainter(img);
            p.setRenderHint(QPainter.Antialiasing)
            p.translate(10, 10);
            p.rotate(i * 45)
            p.setPen(Qt.NoPen);
            p.setBrush(QColor("#228b22").lighter(150))
            p.drawPath(path);
            p.end()
            self.dir_series_map[d].setBrush(QBrush(img))
            self.dir_series_map[d].setMarkerShape(QScatterSeries.MarkerShapeRectangle)
            self.dir_series_map[d].setMarkerSize(20);
            self.dir_series_map[d].setBorderColor(Qt.transparent)

    def chart_image(self):
        # Wir erstellen ein QImage in der Größe des Charts
        image = QImage(self.chart.size().toSize(), QImage.Format_ARGB32)
        image.fill(Qt.transparent)  # Optional, da der Verlauf alles füllt

        # Ein Painter rendert das komplette Chart-Objekt (inkl. BackgroundBrush)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        self.chart.scene().render(painter)
        painter.end()
        return image

    def close_window(self):
        self.close()

    def keyPressEvent(self, event):
        # Screenshot-Funktion mit Strg+S
        if event.key() == Qt.Key_S and (event.modifiers() & Qt.ControlModifier):

            image = self.chart_image()

            # Speichern des Bildes
            filename = f"wetter_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            if image.save(filename):
                logger.info(f"Chart erfolgreich gespeichert: {filename}")

            else:
                logger.error("Fehler beim Speichern des Charts.")

        elif event.key() == Qt.Key_Escape:
            logger.debug("Chart-Fenster per Esc geschlossen.")
            self.close_window()

        # Plus-Taste auf dem Nummernblock
        elif event.key() == Qt.Key_Plus:

            self.darker -= 1
            self.update_chart_background()
            logger.debug(f"NumPad Plus gedrückt: darker={self.darker}")

        # Minus-Taste auf dem Nummernblock
        elif event.key() == Qt.Key_Minus:
            self.darker += 1
            self.update_chart_background()
            logger.debug(f"NumPad Minus gedrückt: darker={self.darker}")
        else:
            super().keyPressEvent(event)

def show_chart(parent_widget):
    dialog = ChartDialog(parent_widget)
    dialog.setStyleSheet("QDialog { background-color: #000000; }")
    dialog.exec()