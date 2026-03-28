#!/bin/bash

set -e

echo "Installiere Systempakete..."
sudo apt update
sudo apt install -y libjpeg-dev zlib1g-dev

echo "Erstelle virtuelle Umgebung..."
python3.12 -m venv venv

echo "Aktiviere virtuelle Umgebung..."
source venv/bin/activate

echo "Installiere Python-Abhängigkeiten..."
pip install --upgrade pip
pip install -r requirements.txt
pip install python-telegram-bot --upgrade

echo "Fertig! Starte das Programm mit:"
echo "source venv/bin/activate && python main.py"

