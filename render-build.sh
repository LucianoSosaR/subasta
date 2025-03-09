#!/usr/bin/env bash

# Instalar Google Chrome en Render
echo "📥 Instalando Google Chrome..."
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt-get update && sudo apt-get install -y google-chrome-stable

# Instalar dependencias de Python
echo "📥 Instalando dependencias de Python..."
pip install -r requirements.txt

echo "✅ Instalación completa"
