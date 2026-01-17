import os
import logging
from threading import Lock

# --- CONFIGURACIÓN GLOBAL ---
# Aquí definimos las constantes y configuraciones que usa todo el programa.

# os.getcwd() obtiene la carpeta actual donde estás ejecutando el script.
BASE_DIR = os.getcwd()

# os.path.join une partes de una ruta de forma segura (funciona en Windows, Linux, Mac).
# Carpeta temporal para descargas y descompresión.
WORK_DIR = os.path.join(BASE_DIR, "workspace")

# Carpeta donde se guardarán los subtítulos finales generados.
OUT_BASE_DIR = os.path.join(BASE_DIR, "subtitle_out")

# Archivo que actúa como "memoria" para no traducir lo mismo dos veces.
CACHE_FILE = os.path.join(BASE_DIR, "translation_cache.json")

# Archivo donde se guardarán los errores y avisos del programa.
LOG_FILE = os.path.join(BASE_DIR, "subsync.log")

# Archivo que contiene tu clave secreta de Google Gemini.
API_KEY_FILE = os.path.join(BASE_DIR, "apikey.key")

# --- CONFIGURACIÓN DE LOGS ---
# Esto configura el sistema de registro de Python.
# filename: dónde se guarda.
# level: qué importancia mínima registrar (INFO = información general).
# format: cómo se ve cada línea (fecha + mensaje).
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s %(message)s', filemode='w')

# Creamos un objeto 'logger' que usaremos para escribir en el log.
logger = logging.getLogger()

# --- CERROJOS (LOCKS) ---
# Los locks sirven para evitar que dos hilos (procesos paralelos) escriban
# en el mismo archivo o variable memoria a la vez y lo corrompan.
cache_lock = Lock() # Protege el archivo de caché
api_lock = Lock()   # Protege llamadas a la API (si fuera necesario limitar)

# Función para leer la API Key desde el archivo
def get_api_key():
    """Lee el contenido del archivo apikey.key y devuelve el texto limpio."""
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() # .strip() quita espacios y saltos de línea al inicio/final
    return None

# Cargamos la key al iniciar
GOOGLE_API_KEY = get_api_key()
