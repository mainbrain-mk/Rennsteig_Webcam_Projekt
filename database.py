import sqlite3
import os

DB_FILE = "weather.db"

def init_db():
    if not os.path.exists(DB_FILE):
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
                weather_code INTEGER,
                cloud_cover INTEGER,
                pressure REAL
            )
        """)
        conn.commit()
        conn.close()


def save_weather_to_db(data: dict):
    cw = data.get("current", {})
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO weather_log (
            timestamp, temperature, feels_like, humidity,
            wind_speed, wind_dir, wind_gusts, precipitation,
            weather_code, cloud_cover, pressure
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cw.get("time"),
        cw.get("temperature_2m"),
        cw.get("apparent_temperature"),
        cw.get("relative_humidity_2m"),
        cw.get("wind_speed_10m"),
        cw.get("wind_direction_10m"),
        cw.get("wind_gusts_10m"),
        cw.get("precipitation"),
        cw.get("weather_code"),
        cw.get("cloud_cover"),
        cw.get("pressure_msl")
    ))
    conn.commit()
    conn.close()


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