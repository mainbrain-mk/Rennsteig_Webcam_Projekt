import os
from dotenv import load_dotenv

load_dotenv()

URL_WEBCAM = "https://webcam.rennsteigbahn.de/webcam.jpg"

LAT = 50.615521009907944  #50.6548394595539
LON = 10.835310539748429  #10.769355507203136

URL_WEATHER = (
    f"https://api.open-meteo.com/v1/forecast?"
    f"latitude={LAT}&longitude={LON}"
    "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
    "is_day,wind_speed_10m,wind_direction_10m,wind_gusts_10m,"
    "precipitation,rain,showers,snowfall,weather_code,cloud_cover,pressure_msl"
    "&timezone=auto"
)

# Originalgröße des Webcam-Bildes
ORIG_W = 2560
ORIG_H = 1440

# Position des digitalen Rennsteigbahn-Overlays im ORIGINAL-Webcam-Bild
OVERLAY_ORIG_X = 2100
OVERLAY_ORIG_Y = 100
OVERLAY_ORIG_W = 400
OVERLAY_ORIG_H = 160

# Jetzt die Werte aus der Umgebung ziehen
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


