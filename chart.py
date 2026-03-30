import logging
import traceback
from datetime import datetime, timedelta
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QDateTime, QMargins
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

        # Einen vertikalen Farbverlauf definieren
        gradient = QLinearGradient(0, 0, 0, 1)  # Start (0,0) bis Ende (0,1) relativ zur Fläche
        gradient.setCoordinateMode(QGradient.ObjectBoundingMode)  # Wichtig für relative Koordinaten
        gradient.setColorAt(0.0, QColor("#001900"))  # Dunkelblau oben
        gradient.setColorAt(1.0, QColor("#000a1e"))  # Schwarz unten

        # Den Verlauf als Brush für die PlotArea setzen
        self.chart.setBackgroundBrush(QBrush(gradient))
        #self.chart.setPlotAreaBackgroundBrush(QBrush(gradient))

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
        self.axis_x.setLabelsAngle(-45)
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
        for r in rows:
            try:
                dt = datetime.fromisoformat(r[0])
                qt_dt = QDateTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, 0, Qt.UTC)
                ts = float(qt_dt.toMSecsSinceEpoch())
                t, w = float(r[1]), float(r[2])

                self.temp_series.append(ts, t)
                self.wind_series.append(ts, w)
                t_data.append(t)
                if len(r) > 3 and r[3] is not None:
                    f = float(r[3])
                    self.feels_series.append(ts, f)
                    t_data.append(f)
                if dt.hour % 8 == 0 and dt.minute == 0 and len(r) > 4 and r[4] is not None:
                    idx = int((float(r[4]) + 22.5) / 45) % 8
                    self.dir_series_map[directions[idx]].append(ts, w)
            except:
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
            first_dt = datetime.fromisoformat(rows[0][0])
            last_dt = datetime.fromisoformat(rows[-1][0])
            start_py = first_dt.replace(hour=(first_dt.hour // 8) * 8, minute=0, second=0, microsecond=0)
            diff_py = last_dt - start_py
            num_intervals = int(diff_py.total_seconds() // 28800) + 1
            end_py = start_py + timedelta(hours=num_intervals * 8)

            qt_start = QDateTime(start_py.year, start_py.month, start_py.day, start_py.hour, 0, 0, 0, Qt.UTC)
            qt_end = QDateTime(end_py.year, end_py.month, end_py.day, end_py.hour, 0, 0, 0, Qt.UTC)
            ts_start, ts_end = float(qt_start.toMSecsSinceEpoch()), float(qt_end.toMSecsSinceEpoch())

            self.axis_x.setTickCount(num_intervals + 1)
            self.axis_x.setRange(qt_start, qt_end)

            y_min = (int(min(t_data)) // 2) * 2 - 2
            y_max = (int(max(t_data)) // 2) * 2 + 2
            self.axis_y_temp.setRange(y_min, y_max)
            self.axis_y_temp.setTickCount(int((y_max - y_min) / 2) + 1)
            self.axis_y_wind.setRange(0, 32);
            self.axis_y_wind.setTickCount(5)

            # --- DAS MANUELLE FARB-GITTER ---
            for val in range(y_min, y_max + 1, 2):
                grid_line = QLineSeries()
                if val == 0:
                    pen = QPen(QColor("#4fc3f7"), 1, Qt.SolidLine)  # Basis 0°C
                elif val > 0:
                    # Grüner werdend (Richtung +)
                    green_val = min(255, 100 + val * 20)
                    pen = QPen(QColor(40, green_val, 40, 180), 1, Qt.DotLine)
                else:
                    # Blauer werdend (Richtung -)
                    blue_val = min(255, 120 + abs(val) * 25)
                    pen = QPen(QColor(40, 60, blue_val, 180), 1, Qt.DotLine)

                grid_line.setPen(pen)
                grid_line.append(ts_start, val)
                grid_line.append(ts_end, val)
                self.chart.addSeries(grid_line)
                grid_line.attachAxis(self.axis_x)
                grid_line.attachAxis(self.axis_y_temp)
                # Aus Legende entfernen
                m = self.chart.legend().markers(grid_line)
                if m: m[0].setVisible(False)

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

    def keyPressEvent(self, event):
        # Screenshot-Funktion mit Strg+S
        if event.key() == Qt.Key_S and (event.modifiers() & Qt.ControlModifier):
            # Wir erstellen ein QImage in der Größe des Charts
            image = QImage(self.chart.size().toSize(), QImage.Format_ARGB32)
            image.fill(Qt.transparent)  # Optional, da der Verlauf alles füllt

            # Ein Painter rendert das komplette Chart-Objekt (inkl. BackgroundBrush)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing)
            self.chart.scene().render(painter)
            painter.end()

            # Speichern des Bildes
            filename = f"wetter_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            if image.save(filename):
                logger.info(f"Chart erfolgreich gespeichert: {filename}")
            else:
                logger.error("Fehler beim Speichern des Charts.")
        else:
            super().keyPressEvent(event)

def show_chart(parent_widget):
    dialog = ChartDialog(parent_widget)
    dialog.setStyleSheet("QDialog { background-color: #000000; }")
    dialog.exec()