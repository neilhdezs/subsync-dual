#!/usr/bin/env python3
# /// script
# dependencies = ["pysubs2", "google-generativeai", "cloudscraper", "beautifulsoup4", "questionary", "rich"]
# ///

# Importaciones de librerías estándar de Python
import os
import shutil
import time
import urllib.parse
import re
from concurrent.futures import ThreadPoolExecutor

# Importaciones de librerías externas (instaladas con uv/pip)
import questionary
from rich.panel import Panel
from rich.live import Live

# --- IMPORTACIONES DE NUESTROS MÓDULOS (src/) ---
# Aquí es donde conectamos todas las piezas que hemos separado.
from src.config import WORK_DIR, OUT_BASE_DIR, GOOGLE_API_KEY
from src.ui import console, LogManager, create_progress, get_dynamic_layout
from src.utils import search_series, download_and_extract, save_cache
from src.subtitle import process_episode

def main():
    # 1. Mensaje de Bienvenida (Banner Azul)
    console.print(Panel("[bold white on blue] SUBSYNC: GEMINI 2.5 FLASH-LITE (MODULAR MOD) [/bold white on blue]"))
    
    # Verificación de Seguridad: Si no hay llave, no podemos trabajar.
    if not GOOGLE_API_KEY: 
        console.print("[red]Falta apikey.key[/red]")
        return

    # 2. Interrogatorio al Usuario (Search)
    # Preguntamos qué serie quiere buscar.
    query = questionary.text("Serie:").ask()
    if not query: return
    
    # Buscamos en la web (usando src.utils.search_series)
    results = search_series(query)
    if not results: return

    # Le damos a elegir entre los resultados encontrados.
    choice = questionary.select("Elige:", choices=[r['display'] for r in results]).ask()
    selected = next(r for r in results if r['display'] == choice)
    
    # 3. Datos de Temporadas y Hilos
    s_in = questionary.text("Temporada ('n' para todas):").ask()
    
    # Lógica para "Todas las temporadas" vs "Lista específica"
    if s_in.lower() in ['1-n', 'all', 'n']: 
        s_list = None # None significa "Sigue hasta que no encuentres más"
    else: 
        s_list = [int(x) for x in s_in.split(',') if x.strip().isdigit()]
    
    # Preguntamos potencia de fuego (hilos paralelos)
    threads_in = questionary.text("Hilos (Enter = 8):", default="8").ask()
    try: max_threads = int(threads_in)
    except: max_threads = 8

    # --- BUCLE PRINCIPAL DE TEMPORADAS ---
    idx = 0
    while True:
        # Calculamos cuál es la siguiente temporada a procesar
        if s_list is None: 
            s_num = idx + 1 # Modo automático (1, 2, 3...)
        else:
            if idx >= len(s_list): break # Se acabaron las de la lista
            s_num = s_list[idx]
        
        # Límite de seguridad por si acaso (nadie tiene 50 temporadas... excepto Los Simpsons)
        if s_num > 50: break
        idx += 1

        # Separador visual en la consola
        console.rule(f"Temporada {s_num}")
        
        # Limpieza: Borramos la carpeta de trabajo anterior para empezar limpitos.
        if os.path.exists(WORK_DIR): shutil.rmtree(WORK_DIR)
        os.makedirs(os.path.join(WORK_DIR, "en"), exist_ok=True)
        
        # Construimos la URL de descarga de "TVSubtitles.net"
        # Quitamos años y paréntesis para que cuadre con la URL de la web.
        clean_name = re.sub(r'\s*\(\d{4}-.*?\)', '', selected['display']).replace("(","").replace(")","").strip()
        url = f"https://www.tvsubtitles.net/files/seasons/{urllib.parse.quote(clean_name)}%20-%20season%20{s_num}.en.zip"
        
        # Descargamos y descomprimimos (src.utils)
        success = download_and_extract(url)
        if not success: 
            # Si falla y estábamos en modo automático, asumimos que se acabaron las temporadas.
            if s_list is None: break
            continue # Si era una lista específica, probamos con la siguiente.
            
        # Preparamos carpeta de destino
        out_dir = os.path.join(OUT_BASE_DIR, clean_name.replace(" ","_"), f"Season_{s_num}")
        os.makedirs(out_dir, exist_ok=True)
        
        # Listamos todos los archivos .srt que hemos descomprimido
        files = sorted([f for f in os.listdir(os.path.join(WORK_DIR, "en")) if f.endswith(('.srt', '.sub'))])
        
        # --- PREPARACIÓN DE LA INTERFAZ (UI) ---
        progress = create_progress()
        log_mgr = LogManager(max_len=12)
        
        # Live Context Manager: Se encarga de repintar la pantalla constantemente sin parpadear.
        with Live(get_dynamic_layout(progress, log_mgr), refresh_per_second=5) as live:
            
            # ThreadPoolExecutor: El motor que ejecuta varias cosas a la vez.
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                futures = []
                # Lanzamos una tarea (hilo) por cada archivo de subtítulo
                for f in files:
                    # Añadimos una barrita a la UI
                    tid = progress.add_task("Wait", filename=f[:12], total=100)
                    # Enviamos la tarea al 'pool' de hilos
                    futures.append(executor.submit(
                        process_episode, # Función a ejecutar (src.subtitle)
                        f, os.path.join(WORK_DIR, "en"), out_dir, clean_name, progress, tid, log_mgr
                    ))
                
                # Bucle de espera activa: Mantiene la UI viva mientras los hilos trabajan.
                while any(f.running() for f in futures):
                     live.update(get_dynamic_layout(progress, log_mgr))
                     time.sleep(0.2) # Dormimos un pelín para no quemar la CPU repintando
                
                # Aseguramos que todos hayan terminado (y lanzamos excepciones si las hubo)
                for f in futures: f.result()
               
        # Guardamos el caché de traducciones al disco al terminar cada temporada
        save_cache()
        
        # Si era una lista de temporadas específica, y ya acabamos esta vuelta... next!
        if s_list and idx >= len(s_list): break
        # Si era modo "All" y descargamos bien, el bucle sigue al principio (idx++)

    console.print("[bold green]Listo. Proyecto completado.[/bold green]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Si el usuario pulsa Ctrl+C, salimos elegantemente.
        console.print("\n[bold yellow]Interrupción de usuario detectada. Saliendo...[/bold yellow]")
        os._exit(0)
