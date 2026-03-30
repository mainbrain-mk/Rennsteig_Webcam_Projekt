import logging
from datetime import datetime, timedelta
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QDateTime
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QDateTimeAxis, QValueAxis, QScatterSeries
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QTransform, QImage, QBrush

from database import load_last_7_days

logger = logging.getLogger(__name__)


class ChartDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wetterverlauf Rennsteigbahn – Modern")
        self.resize(1280, 720)

        layout = QVBoxLayout(self)

        rows = load_last_7_days()
        if not rows:
            layout.addWidget(QLabel("Keine Daten in der Datenbank gefunden."))
            return

        # --- 1. Datenreihen & Styling (unverändert) ---
        temp_series = QLineSeries()
        temp_series.setName("Temperatur (°C)")
        wind_series = QLineSeries()
        wind_series.setName("Wind (km/h)")
        feels_like_series = QLineSeries()
        feels_like_series.setName("Gefühlt (°C)")

        directions = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"]
        dir_series_map = {d: QScatterSeries() for d in directions}

        # Pfeil-Design (unverändert)
        arrow_path = QPainterPath()
        arrow_path.moveTo(0, 11);
        arrow_path.lineTo(-6, -6);
        arrow_path.lineTo(0, -3);
        arrow_path.lineTo(6, -6);
        arrow_path.closeSubpath()

        for d_name, s in dir_series_map.items():
            s.setName(f"Wind: {d_name}");
            s.setBorderColor(Qt.transparent);
            s.setMarkerSize(26)
            img = QImage(24, 24, QImage.Format_ARGB32);
            img.fill(Qt.transparent)
            p = QPainter(img);
            p.setRenderHint(QPainter.Antialiasing);
            p.translate(12, 12)
            p.rotate(directions.index(d_name) * 45);
            p.setPen(Qt.NoPen);
            p.setBrush(QColor("#228b22").lighter(150))
            p.drawPath(arrow_path);
            p.end()
            s.setBrush(QBrush(img));
            s.setMarkerShape(QScatterSeries.MarkerShapeRectangle)

        # --- 2. Daten laden ---
        for r in rows:
            try:
                dt = datetime.fromisoformat(r[0])
                ts = QDateTime(dt).toMSecsSinceEpoch()
                temp_series.append(ts, r[1])
                wind_series.append(ts, r[2])
                if len(r) > 3: feels_like_series.append(ts, r[3])
                # Windpfeile nur an 8h-Marken (0, 8, 16)
                if dt.hour % 8 == 0 and dt.minute == 0:
                    if len(r) > 4:
                        deg = r[4];
                        idx = int((deg + 22.5) / 45) % 8
                        dir_series_map[directions[idx]].append(ts, r[2])
            except (ValueError, IndexError):
                continue

        # --- 3. Chart & Achsen-Setup ---
        chart = QChart()
        chart.setTitle("Wetterdaten der letzten 7 Tage")
        chart.setTheme(QChart.ChartThemeDark)

        axis_x = QDateTimeAxis()
        axis_x.setFormat("dd. HH:mm")
        axis_x.setGridLineVisible(False)  # Wir zeichnen selbst
        chart.addAxis(axis_x, Qt.AlignBottom)

        axis_y_temp = QValueAxis()
        axis_y_temp.setTitleText("Temperatur [°C]")
        axis_y_temp.setGridLineVisible(False)
        chart.addAxis(axis_y_temp, Qt.AlignLeft)

        # --- 4. Y-Skalierung (Temperatur) ---
        all_t = [p.y() for p in temp_series.points()] + [p.y() for p in feels_like_series.points()]
        y_min = (int(min(all_t)) // 2) * 2 - 2 if all_t else -10
        y_max = (int(max(all_t)) // 2) * 2 + 2 if all_t else 10
        num_ticks_y = int((y_max - y_min) / 2) + 1
        axis_y_temp.setRange(y_min, y_max)
        axis_y_temp.setTickCount(num_ticks_y)
        axis_y_temp.setLabelFormat("%d")

        # --- 5. Fixiertes 8h-Raster für X-Achse ---
        if rows:
            first_dt = datetime.fromisoformat(rows[0][0])
            last_dt = datetime.fromisoformat(rows[-1][0])

            # Start: Letzte glatte 8h-Marke (0, 8, 16)
            start_hour = (first_dt.hour // 8) * 8
            base_start = first_dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)

            # Ende: Nächste glatte 8h-Marke nach dem letzten Datenpunkt
            end_dt = last_dt.replace(minute=0, second=0, microsecond=0)
            while end_dt.hour % 8 != 0 or end_dt < last_dt:
                end_dt += timedelta(hours=1)

            axis_x.setRange(QDateTime(base_start), QDateTime(end_dt))

            # TickCount erzwingen: (Gesamtstunden / 8) + 1
            total_hours = (end_dt - base_start).total_seconds() / 3600
            axis_x.setTickCount(int(total_hours // 8) + 1)

            # Manuelles vertikales Gitter
            curr = base_start
            while curr <= end_dt:
                v_line = QLineSeries()
                ts = QDateTime(curr).toMSecsSinceEpoch()
                v_line.append(ts, y_min);
                v_line.append(ts, y_max)
                v_line.setPen(QPen(QColor(75, 75, 75), 1))
                chart.addSeries(v_line)
                v_line.attachAxis(axis_x);
                v_line.attachAxis(axis_y_temp)
                chart.legend().markers(v_line)[0].setVisible(False)
                curr += timedelta(hours=8)

        # --- 6. Horizontales Gitter (Temperatur) ---
        curr_y = y_min
        while curr_y <= y_max:
            h_line = QLineSeries()
            h_line.append(axis_x.min().toMSecsSinceEpoch(), curr_y)
            h_line.append(axis_x.max().toMSecsSinceEpoch(), curr_y)
            col = QColor("#4fc3f7") if curr_y == 0 else (QColor(40, 60, 120) if curr_y < 0 else QColor(50, 80, 50))
            h_line.setPen(QPen(col, 1, Qt.DashLine if curr_y != 0 else Qt.SolidLine))
            chart.addSeries(h_line)
            h_line.attachAxis(axis_x);
            h_line.attachAxis(axis_y_temp)
            chart.legend().markers(h_line)[0].setVisible(False)
            curr_y += 2

        # --- 7. Wind-Achse (Rechts) ---
        axis_y_wind = QValueAxis()
        axis_y_wind.setTitleText("Wind [km/h]");
        axis_y_wind.setGridLineVisible(False)
        chart.addAxis(axis_y_wind, Qt.AlignRight)

        all_w = [p.y() for p in wind_series.points()]
        w_max_limit = (int(max(all_w) / (num_ticks_y - 1)) + 1) * (num_ticks_y - 1) if all_w else 30
        axis_y_wind.setRange(0, max(w_max_limit, (num_ticks_y - 1) * 3))
        axis_y_wind.setTickCount(num_ticks_y)
        axis_y_wind.setLabelFormat("%.1f")

        # --- 8. Finale Bindung ---
        for s, ax_y in [(temp_series, axis_y_temp), (feels_like_series, axis_y_temp), (wind_series, axis_y_wind)]:
            chart.addSeries(s);
            s.attachAxis(axis_x);
            s.attachAxis(ax_y)

        temp_series.setPen(QPen(QColor("#0078d4"), 3))
        feels_like_series.setPen(QPen(QColor("#4fc3f7"), 2, Qt.DotLine))
        wind_series.setPen(QPen(QColor("#228b22"), 2, Qt.DashLine))

        for s in dir_series_map.values():
            chart.addSeries(s)
            s.attachAxis(axis_x)
            s.attachAxis(axis_y_wind)
            chart.legend().markers(s)[0].setVisible(False)

        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.Antialiasing)
        layout.addWidget(chart_view)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_S and (event.modifiers() & Qt.ControlModifier):
            chart_view = self.findChild(QChartView)
            if chart_view:
                image = QImage(chart_view.size(), QImage.Format_ARGB32)
                image.fill(Qt.transparent)
                painter = QPainter(image)
                chart_view.render(painter)
                painter.end()
                filename = f"wetter_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                if image.save(filename, "PNG"):
                    print(f"Chart gespeichert: {filename}")
        else:
            super().keyPressEvent(event)


def show_chart(parent_widget):
    dialog = ChartDialog(parent_widget)
    dialog.exec()