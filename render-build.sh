#!/bin/bash

echo "🔹 Instalando Chromium..."
apt-get update && apt-get install -y chromium-browser

echo "🔹 Instalando dependencias de Python..."
pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Configuración completa."
