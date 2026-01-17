import os
import json
import shutil
import zipfile
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
# Importaciones propias
from src.config import CACHE_FILE, WORK_DIR, cache_lock, logger
import cloudscraper
from bs4 import BeautifulSoup

# --- CACHÉ DE TRADUCCIONES ---
# Cargamos el archivo JSON en memoria para no pedirle a la IA lo que ya tradujo antes.
TRANSLATION_CACHE = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, 'r') as f:
            TRANSLATION_CACHE = json.load(f)
    except:
        pass # Si falla al leer, empezamos con caché vacía.

def save_cache():
    """Guarda la memoria RAM (TRANSLATION_CACHE) en el disco duro (json)."""
    with cache_lock:
        with open(CACHE_FILE, 'w') as f:
            json.dump(TRANSLATION_CACHE, f, ensure_ascii=False)

# --- SCRAPER (Buscador de Subtítulos) ---
# Usamos cloudscraper para saltarnos la protección de Cloudflare de la web.
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})

def search_series(query):
    """Busca una serie en tvsubtitles.net y devuelve resultados."""
    try:
        # Hacemos una petición POST (como enviar un formulario) con el nombre de la serie.
        resp = scraper.post("https://www.tvsubtitles.net/search.php", data={'qs': query})
        
        # BeautifulSoup parsea el HTML para que podamos buscar etiquetas <a> (enlaces).
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Buscamos todos los links que parezcan series ("/tvshow-123.html")
        results = []
        for a in soup.find_all('a', href=re.compile(r'/tvshow-\d+\.html')):
            results.append({
                "display": a.get_text().strip(), # Texto visible (ej: "Friends")
                "href": a['href']                # Enlace interno
            })
        return results
    except Exception as e:
        logger.error(f"Error buscando serie: {e}")
        return []

def download_and_extract(url):
    """Descarga el ZIP de subtítulos y lo descomprime en la carpeta de trabajo."""
    # 1. Limpiar carpeta anterior
    if os.path.exists(WORK_DIR): shutil.rmtree(WORK_DIR)
    os.makedirs(os.path.join(WORK_DIR, "en"), exist_ok=True)
    
    # 2. Descargar
    r = scraper.get(url)
    if r.status_code != 200: return False # Si falló la descarga
    
    # 3. Guardar ZIP temporalmente
    zip_path = os.path.join(WORK_DIR, "temp_subs.zip")
    with open(zip_path, "wb") as f: f.write(r.content)
    
    # 4. Descomprimir
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(os.path.join(WORK_DIR, "en"))
        
    # 5. Borrar el ZIP para no dejar basura
    try: os.remove(zip_path)
    except: pass
    
    return True
