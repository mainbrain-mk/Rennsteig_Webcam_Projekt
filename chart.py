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

        # Series (Datenreihen) erstellen
        temp_series = QLineSeries()
        temp_series.setName("Temperatur (°C)")

        wind_series = QLineSeries()
        wind_series.setName("Wind (km/h)")

        feels_like_series = QLineSeries()
        feels_like_series.setName("Gefühlt (°C)")

        # Vorbereitung für Windrichtung (8 Himmelsrichtungen)
        directions = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"]
        dir_series_map = {}

        arrow_path = QPainterPath()
        # Koordinaten vergrößert, damit der Pfeil mehr von der 24x24 Fläche nutzt
        arrow_path.moveTo(0, 11)  # Spitze
        arrow_path.lineTo(-6, -6)  # Unten links
        arrow_path.lineTo(0, -3)  # Einbuchtung
        arrow_path.lineTo(6, -6)  # Unten rechts
        arrow_path.closeSubpath()

        for d_name in directions:
            s = QScatterSeries()
            s.setName(f"Wind: {d_name}")

            s.setBorderColor(Qt.transparent)
            s.setPen(Qt.NoPen)

            s.setMarkerSize(26)  # Etwas größer für bessere Sichtbarkeit

            # --- Pfeil-Icon als Bild rendern ---
            img = QImage(24, 24, QImage.Format_ARGB32)
            img.fill(Qt.transparent)

            painter = QPainter(img)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.translate(12, 12)  # In die Mitte des Bildes springen

            angle = directions.index(d_name) * 45
            painter.rotate(angle)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#228b22").lighter(150))  # Wind-Grün
            painter.drawPath(arrow_path)
            painter.end()

            # Bild als Brush für die Serie setzen
            s.setBrush(QBrush(img))
            s.setMarkerShape(QScatterSeries.MarkerShapeRectangle)  # Container für das Bild
            dir_series_map[d_name] = s

        marked_hours = set()

        # Daten-Schleife erweitern
        for r in rows:
            try:
                dt = datetime.fromisoformat(r[0])
                ts = QDateTime(dt).toMSecsSinceEpoch()

                # Standard-Daten (bleiben erhalten!)
                temp_series.append(ts, r[1])
                wind_val = r[2]
                wind_series.append(ts, wind_val)
                if len(r) > 3: feels_like_series.append(ts, r[3])

                hour_key = f"{dt.date()}_{dt.hour}"
                if dt.hour % 4 == 0 and dt.minute < 15 and hour_key not in marked_hours:
                    if len(r) > 4:
                        deg = r[4]
                        idx = int((deg + 22.5) / 45) % 8
                        dir_name = directions[idx]
                        dir_series_map[dir_name].append(ts, wind_val)
                        marked_hours.add(hour_key)  # Diesen Block als erledigt markieren

            except ValueError:
                continue

        # Chart-Objekt konfigurieren
        chart = QChart()
        chart.addSeries(temp_series)
        chart.addSeries(wind_series)
        chart.addSeries(feels_like_series)
        chart.setTitle("Wetterdaten der letzten 7 Tage")
        chart.setAnimationOptions(QChart.SeriesAnimations)  # Schicke Animation beim Öffnen
        chart.setTheme(QChart.ChartThemeDark)

        # X-Achse (Zeit) – Fixiert auf 4h-Raster
        axis_x = QDateTimeAxis()
        axis_x.setFormat("dd.MM. HH:mm")
        axis_x.setTitleText("Zeitpunkt")

        if rows:
            first_dt = datetime.fromisoformat(rows[0][0])
            last_dt = datetime.fromisoformat(rows[-1][0])

            # Trick: Wir finden die letzte glatte 4h-Marke VOR den Daten
            # Beispiel: 22:15 -> 20:00
            start_hour_aligned = (first_dt.hour // 4) * 4
            base_start = first_dt.replace(hour=start_hour_aligned, minute=0, second=0, microsecond=0)

            # Wir berechnen, wie viele 4h-Schritte wir bis nach dem Ende brauchen
            total_delta = last_dt - base_start
            total_hours = total_delta.total_seconds() / 3600

            # Anzahl der Ticks so wählen, dass der letzte Tick hinter den Daten liegt
            tick_count = int(total_hours // 4) + 2

            # Das Ende der Achse ist exakt (Anzahl Ticks - 1) * 4 Stunden nach dem base_start
            end_aligned = base_start + timedelta(hours=(tick_count - 1) * 4)

            # Jetzt setzen wir den Bereich so, dass er bei den ECHTEN Daten startet,
            # aber wir passen den Tick-Count so an, dass die Ticks auf den 4h-Marken landen.
            # Da QtCharts das nicht nativ "offsetten" kann, ist der sauberste Weg für
            # ein festes Raster, die Achse dezent zu erweitern:

            axis_x.setRange(QDateTime(base_start), QDateTime(end_aligned))
            axis_x.setTickCount(tick_count)

        chart.addAxis(axis_x, Qt.AlignBottom)

        temp_series.attachAxis(axis_x)
        wind_series.attachAxis(axis_x)
        feels_like_series.attachAxis(axis_x)

        # --- Y-Achse Temperatur (Links) ---
        axis_y_temp = QValueAxis()
        axis_y_temp.setTitleText("Temperatur [°C]")

        # Puffer berechnen
        all_temps = [p.y() for p in temp_series.points()]

        if feels_like_series.points():
            all_temps += [p.y() for p in feels_like_series.points()]

        if all_temps:
            y_min, y_max = min(all_temps), max(all_temps)
            logger.debug(f"y_min: {y_min}, y_max: {y_max}")


            y_min -= 2
            y_max += 2


            # Anzahl der Ticks für exakte 2-Grad-Schritte berechnen
            num_ticks = int((y_max - y_min) / 2) + 1

            axis_y_temp.setRange(y_min, y_max)
            axis_y_temp.setTickCount(num_ticks)
            axis_y_temp.setLabelFormat("%d")  # Zeigt nur Ganzzahlen


        chart.addAxis(axis_y_temp, Qt.AlignLeft)
        temp_series.attachAxis(axis_y_temp)
        feels_like_series.attachAxis(axis_y_temp)

        axis_y_temp.setGridLineVisible(False)

        if all_temps:
            # Wir erstellen eigene Linien-Serien für das Gitter
            # Schrittweite 2 (passend zu deinem Tick-Count)
            current_y = int(y_min)
            while current_y <= y_max:
                grid_line = QLineSeries()

                # Start- und Endpunkt (Zeitachse)
                grid_line.append(axis_x.min().toMSecsSinceEpoch(), current_y)
                grid_line.append(axis_x.max().toMSecsSinceEpoch(), current_y)

                # Farblogik
                if current_y == 0:
                    # Die gewünschte hellblaue Null-Linie
                    color = QColor("#4fc3f7")
                    width = 1
                    style = Qt.DashLine
                elif current_y < 0:
                    # Blau-Verlauf: Je kälter, desto gesättigter/dunkler
                    # Wir nutzen eine Basis-Intensität und addieren den Kältegrad
                    blue_val = min(255, 120 + abs(current_y) * 10)
                    color = QColor(30, 80, blue_val)
                    width = 1
                    style = Qt.DashLine
                else:
                    # Grün-Verlauf: Je wärmer, desto kräftiger das Grün
                    green_val = min(255, 100 + current_y * 8)
                    color = QColor(20, green_val, 40)
                    width = 1
                    style = Qt.DashLine

                grid_line.setPen(QPen(color, width, style))

                # Zum Chart hinzufügen (vor den Daten-Serien, damit sie im Hintergrund liegen)
                chart.addSeries(grid_line)
                grid_line.attachAxis(axis_x)
                grid_line.attachAxis(axis_y_temp)

                # Aus der Legende entfernen
                chart.legend().markers(grid_line)[0].setVisible(False)

                current_y += 2

        # --- Y-Achse Wind (Rechts) ---
        axis_y_wind = QValueAxis()
        axis_y_wind.setTitleText("Wind [km/h]")

        all_winds = [p.y() for p in wind_series.points()]
        if all_winds:
            w_max = max(all_winds)
            # Wind startet meist bei 0, also nur Puffer nach oben
            axis_y_wind.setRange(0, w_max * 1.2 if w_max > 0 else 10)

        axis_y_wind.setTickCount(num_ticks)  # Gleiche Anzahl wie Temperatur für sauberes Gitter
        chart.addAxis(axis_y_wind, Qt.AlignRight)
        wind_series.attachAxis(axis_y_wind)

        axis_y_wind.setGridLineVisible(False)

        # Styling der Linien
        temp_pen = QPen(QColor("#0078d4"), 3)
        temp_series.setPen(temp_pen)

        feels_pen = QPen(QColor("#4fc3f7"), 2)  # Hellblau
        feels_pen.setStyle(Qt.DotLine)  # Gepunktet, um sie von der echten Temp zu unterscheiden
        feels_like_series.setPen(feels_pen)

        wind_pen = QPen(QColor("#228b22"), 2)
        wind_pen.setStyle(Qt.DashLine)
        wind_series.setPen(wind_pen)

        # Alle Richtungs-Serien dem Chart hinzufügen und binden
        for s in dir_series_map.values():
            chart.addSeries(s)
            s.attachAxis(axis_x)
            s.attachAxis(axis_y_wind)  # Pfeile "kleben" an der Wind-Skala rechts
            # Optional: Aus der Legende ausblenden, damit es nicht zu voll wird
            chart.legend().markers(s)[0].setVisible(False)

        # Viewport erstellen
        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.Antialiasing)  # Glatte Linien
        layout.addWidget(chart_view)

    def keyPressEvent(self, event):
        # STRG + S
        if event.key() == Qt.Key_S and (event.modifiers() & Qt.ControlModifier):
            # Den Chart-View finden (wir nehmen das Widget aus dem Layout)
            chart_view = self.findChild(QChartView)
            if chart_view:
                # Ein Bild in der Größe des Widgets erstellen
                image = QImage(chart_view.size(), QImage.Format_ARGB32)
                image.fill(Qt.transparent)

                # Den Inhalt des ChartViews in das Bild zeichnen
                painter = QPainter(image)
                chart_view.render(painter)
                painter.end()

                # Speichern (Dateiname mit Zeitstempel)
                filename = f"wetter_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                if image.save(filename, "PNG"):
                    print(f"Chart erfolgreich gespeichert als {filename}")
        else:
            super().keyPressEvent(event)

def show_chart(parent_widget):
    dialog = ChartDialog(parent_widget)
    dialog.exec()