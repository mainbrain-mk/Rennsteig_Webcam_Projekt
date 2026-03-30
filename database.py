import logging
import sqlite3
import os

logger = logging.getLogger(__name__)

DB_FILE = "weather.db"

def init_db():
    if not os.path.exists(DB_FILE):
        """Initialisiert die Datenbank mit der vollständigen Struktur."""
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS weather_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT UNIQUE,
                temperature REAL,
                feels_like REAL,
                humidity INTEGER,
                wind_speed REAL,
                wind_dir INTEGER,
                wind_gusts REAL,
                precipitation REAL,
                rain REAL,
                showers REAL,
                snowfall REAL,
                weather_code INTEGER,
                cloud_cover INTEGER,
                pressure REAL
            )
        """)
        conn.commit()
        conn.close()

def save_weather_to_db(data: dict):
    """Speichert die erweiterten Daten inklusive rain, showers und snowfall."""
    if not data or "current" not in data:
        return

    cw = data.get("current", {})
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Das SQL Statement nutzt nun die von dir vorbereiteten Spalten
        c.execute("""
            INSERT OR IGNORE INTO weather_log (
                timestamp, temperature, feels_like, humidity,
                wind_speed, wind_dir, wind_gusts, precipitation,
                rain, showers, snowfall,
                weather_code, cloud_cover, pressure, is_day
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cw.get("time"),
            cw.get("temperature_2m"),
            cw.get("apparent_temperature"),
            cw.get("relative_humidity_2m"),
            cw.get("wind_speed_10m"),
            cw.get("wind_direction_10m"),
            cw.get("wind_gusts_10m"),
            cw.get("precipitation"),
            cw.get("rain"), # NEU
            cw.get("showers"), # NEU
            cw.get("snowfall"), # NEU
            cw.get("weather_code"),
            cw.get("cloud_cover"),
            cw.get("pressure_msl"),
            cw.get("is_day")
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Fehler beim Speichern in weather.db: {e}")


def load_last_7_days():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT timestamp, temperature, wind_speed, feels_like, wind_dir
        FROM weather_log
        WHERE timestamp >= datetime('now', '-7 days')
        ORDER BY timestamp ASC
    """)
    rows = c.fetchall()
    conn.close()
    return rows