import os
import time
import re
import psycopg2
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# =========================================
# CONFIGURACIÓN
# =========================================
SCRAPE_URL = "https://www.bavastronline.com.uy/auctions/2153"  # URL de la subasta
DATABASE_URL = os.getenv("DATABASE_URL")  # Variable de entorno con la conexión a PostgreSQL

if not DATABASE_URL:
    raise ValueError("❌ ERROR: La variable de entorno DATABASE_URL no está configurada.")

# =========================================
# CONFIGURACIÓN SELENIUM
# =========================================
options = Options()
options.binary_location = "/usr/bin/google-chrome-stable"  # Ubicación de Chrome en Render
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--disable-blink-features=AutomationControlled")

# Inicializar WebDriver con Chrome
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def parse_auction_id(url: str) -> str:
    """Extrae el identificador de la subasta a partir de la URL."""
    match = re.search(r"auctions/(\d+)", url)
    return match.group(1) if match else "N/A"

# =========================================
# FUNCIONES DE SCRAPING
# =========================================
def scroll_down():
    """Realiza scroll hasta que se carguen todos los artículos."""
    scroll_pause_time = 2
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_pause_time)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def scrape_subastas(auction_url: str):
    """Extrae información de los artículos en la subasta."""
    driver.get(auction_url)
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//*[@id='root']/div[1]/div/div/div[4]/div/div/div"))
    )
    
    # Capturar el ID de la subasta desde la URL
    subasta_id = parse_auction_id(auction_url)
    
    # Realiza scroll para cargar todos los artículos
    scroll_down()
    
    # Ejecuta JavaScript para extraer la información de cada tarjeta
    articulos = driver.execute_script("""
    let elements = document.querySelectorAll('.MuiCard-root');
    let data = [];
    elements.forEach((item) => {
        let loteElem = item.querySelector('.MuiTypography-body2');
        let lote = loteElem ? loteElem.innerText.trim() : 'N/A';
        
        let desElems = item.querySelectorAll('.MuiTypography-body2');
        let descripcion = desElems.length > 1 ? desElems[1].innerText.trim() : 'N/A';
        
        let precioElem = item.querySelector('.MuiTypography-body1');
        let precio = precioElem ? precioElem.innerText.trim() : 'N/A';
        
        let ofertas = 0;
        let pElems = item.querySelectorAll('p');
        pElems.forEach((p) => {
            if (p.innerText.includes("Ofertas:")) {
                let bElem = p.querySelector("b");
                if(bElem) {
                    let num = parseInt(bElem.innerText.replace(/[^0-9]/g, ""));
                    if(!isNaN(num)) { ofertas = num; }
                }
            }
        });
        
        let imgElem = item.querySelector('img');
        let imagen = imgElem ? imgElem.src : 'N/A';
        
        let enlaceElem = item.querySelector('a');
        let enlace = enlaceElem ? enlaceElem.href : 'N/A';
        
        data.push([lote, descripcion, precio, ofertas, imagen, enlace]);
    });
    return data;
    """)

    # Agregar subasta_id a cada artículo
    articulos_con_id = [(lote, descripcion, precio, ofertas, imagen, enlace, subasta_id) for (lote, descripcion, precio, ofertas, imagen, enlace) in articulos]

    print(f"✅ Extracción completada: {len(articulos_con_id)} artículos obtenidos (subasta {subasta_id}).")
    return articulos_con_id

# =========================================
# FUNCIONES DE BASE DE DATOS
# =========================================
def update_database(articulos):
    """Guarda o actualiza los datos en la base de datos PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Crear la tabla principal si no existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subastas (
            id SERIAL PRIMARY KEY,
            lote TEXT,
            descripcion TEXT,
            precio TEXT,
            ofertas INTEGER,
            imagen TEXT,
            enlace TEXT UNIQUE,
            subasta_id TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Crear la tabla historial si no existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_subastas (
            id SERIAL PRIMARY KEY,
            lote TEXT,
            descripcion TEXT,
            precio TEXT,
            ofertas INTEGER,
            imagen TEXT,
            enlace TEXT,
            subasta_id TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute("SELECT precio, ofertas, enlace FROM subastas")
    existing = {row[2]: {'precio': row[0], 'ofertas': row[1]} for row in cursor.fetchall()}
    
    for lote, descripcion, precio, ofertas, imagen, enlace, subasta_id in articulos:
        if enlace in existing:
            if precio != existing[enlace]['precio'] or ofertas != existing[enlace]['ofertas']:
                cursor.execute('''
                    UPDATE subastas
                    SET precio = %s, ofertas = %s, subasta_id = %s, timestamp = CURRENT_TIMESTAMP
                    WHERE enlace = %s
                ''', (precio, ofertas, subasta_id, enlace))
                
                cursor.execute('''
                    INSERT INTO historial_subastas (lote, descripcion, precio, ofertas, imagen, enlace, subasta_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (lote, descripcion, precio, ofertas, imagen, enlace, subasta_id))
        else:
            cursor.execute('''
                INSERT INTO subastas (lote, descripcion, precio, ofertas, imagen, enlace, subasta_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (lote, descripcion, precio, ofertas, imagen, enlace, subasta_id))
    
    conn.commit()
    conn.close()

# =========================================
# FLUJO PRINCIPAL
# =========================================
def run_scraper():
    print(f"🔎 Scrapeando subasta en {SCRAPE_URL} ...")
    articulos = scrape_subastas(SCRAPE_URL)
    if articulos:
        update_database(articulos)
        print("✅ Datos guardados.")
    else:
        print("❌ No se encontraron artículos.")

if __name__ == "__main__":
    try:
        run_scraper()
    finally:
        driver.quit()
        print("✅ Script finalizado.")
