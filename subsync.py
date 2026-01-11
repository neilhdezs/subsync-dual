#!/usr/bin/env python3
# /// script
# dependencies = ["pysubs2", "deep-translator", "cloudscraper", "beautifulsoup4", "thefuzz", "questionary", "rich"]
# ///

import os, re, time, zipfile, subprocess, json, urllib.parse, shutil, logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import pysubs2, questionary, cloudscraper
from bs4 import BeautifulSoup
from thefuzz import process
from deep_translator import GoogleTranslator
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.live import Live
from rich.panel import Panel

# --- CONFIGURACIÓN ---
BASE_DIR = os.getcwd()
WORK_DIR = os.path.join(BASE_DIR, "workspace")
OUT_BASE_DIR = os.path.join(BASE_DIR, "Final_Dual_Subs")
CACHE_FILE = os.path.join(BASE_DIR, "translation_cache.json")
LOG_FILE = os.path.join(BASE_DIR, "subsync.log")

# Configuración de Logs
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    filemode='w'
)
logger = logging.getLogger()

console = Console()
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
translator_lock = Lock()
cache_lock = Lock()

# Cargar caché global
TRANSLATION_CACHE = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            TRANSLATION_CACHE = json.load(f)
    except: pass

def save_cache():
    with cache_lock:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(TRANSLATION_CACHE, f, ensure_ascii=False, indent=2)

def clean_workspace():
    if os.path.exists(WORK_DIR):
        shutil.rmtree(WORK_DIR)
    for d in [WORK_DIR, os.path.join(WORK_DIR, "en"), os.path.join(WORK_DIR, "es"), os.path.join(WORK_DIR, "fixed")]:
        os.makedirs(d, exist_ok=True)

def parse_seasons(input_str):
    input_str = str(input_str).lower().strip()
    if input_str in ['all', 'todas', '1-n']: return None
    seasons = []
    try:
        parts = input_str.split(',')
        for part in parts:
            if '-' in part:
                start, end = map(int, part.split('-'))
                seasons.extend(range(start, end + 1))
            else:
                seasons.append(int(part))
    except: return []
    return sorted(list(set(seasons)))

def load_subs_safe(path):
    for enc in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
        try: return pysubs2.load(path, encoding=enc, fps=23.976)
        except: continue
    return None

def get_search_results(query):
    console.print(f"[cyan][*] Buscando '{query}' en TVSubtitles...[/cyan]")
    logger.info(f"Búsqueda iniciada: {query}")
    try:
        resp = scraper.post("https://www.tvsubtitles.net/search.php", data={'qs': query}, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        results = []
        for a in soup.find_all('a', href=re.compile(r'/tvshow-\d+\.html')):
            raw_text = a.get_text().strip()
            href = a['href']
            clean_name = re.sub(r'\s*\(\d{4}-.*?\)', '', raw_text).replace("(", "").replace(")", "").strip()
            show_id = re.search(r'tvshow-(\d+)', href).group(1)
            results.append({"display": raw_text, "clean_name": clean_name, "id": show_id})
        return results
    except Exception as e:
        console.print(f"[red]Error búsqueda: {e}[/red]")
        logger.error(f"Error búsqueda: {e}")
        return []

def download_zip(show_name, show_id, season, lang):
    safe_name = urllib.parse.quote(show_name)
    url = f"https://www.tvsubtitles.net/files/seasons/{safe_name}%20-%20season%20{season}.{lang}.zip"
    dest = os.path.join(WORK_DIR, f"{lang}.zip")
    extract_to = os.path.join(WORK_DIR, lang)

    try:
        r = scraper.get(url, timeout=15)
        if r.status_code == 200 and len(r.content) > 1000:
            with open(dest, 'wb') as f: f.write(r.content)
            with zipfile.ZipFile(dest, 'r') as z: z.extractall(extract_to)
            logger.info(f"Descargado ZIP {lang} Temporada {season}")
            return True
    except Exception as e:
        logger.warning(f"Fallo descarga ZIP {lang} T{season}: {e}")
    return False

def translate_text(text):
    if not text: return ""
    with cache_lock:
        if text in TRANSLATION_CACHE: return TRANSLATION_CACHE[text]
    try:
        with translator_lock:
            time.sleep(0.05)
            trans = GoogleTranslator(source='en', target='es').translate(text)
        with cache_lock:
            TRANSLATION_CACHE[text] = trans
        return trans
    except: return ""

def process_single_episode(f_en, en_dir, es_dir, work_dir, final_out_path, series_folder, progress, task_id):
    try:
        tag_match = re.search(r'(\d+[xXeE]\d+|S\d+E\d+)', f_en, re.IGNORECASE)
        tag = tag_match.group(1).upper() if tag_match else f_en[:10]

        es_files = os.listdir(es_dir)
        best_es = None
        if es_files:
            match_res = process.extractOne(tag, es_files)
            if match_res and match_res[1] > 40: best_es = match_res[0]

        path_en = os.path.join(en_dir, f_en)
        s_en = load_subs_safe(path_en)
        if not s_en:
            progress.update(task_id, description="[red]Error carga EN", completed=100)
            logger.error(f"No se pudo cargar: {f_en}")
            return

        s_es = None
        if best_es:
            progress.update(task_id, description=f"[yellow]Sync {best_es[:10]}...")
            path_es_fixed = os.path.join(work_dir, "fixed", f"{tag}.es.srt")
            tmp_es = load_subs_safe(os.path.join(es_dir, best_es))
            if tmp_es:
                tmp_es.save(path_es_fixed, encoding="utf-8")
                subprocess.run(["alass", path_en, path_es_fixed, path_es_fixed], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                s_es = pysubs2.load(path_es_fixed)
        else:
            logger.warning(f"{tag}: Sin par español. Usando traducción pura.")

        progress.update(task_id, description=f"[magenta]Fusionando...", total=len(s_en))

        # --- LÓGICA ANTI-ECO ---
        last_match_txt = "" 

        for i, line in enumerate(s_en):
            txt = line.text.replace("\\N", " ").strip()
            if not txt: continue

            match_txt = ""
            if s_es:
                # Obtenemos fragmentos que solapan
                ms = [l.text.replace("\\N", " ").strip() for l in s_es if l.start < line.end and l.end > line.start]
                # Anti-Eco Intra-línea: Deduplicamos fragmentos idénticos manteniendo orden
                match_txt = " ".join(list(dict.fromkeys(ms)))

            # Si no hay par sincronizado, traducimos
            if not match_txt:
                match_txt = translate_text(txt)

            if match_txt:
                # Anti-Eco Inter-línea: Si el texto español es igual al anterior, no lo repetimos
                if match_txt == last_match_txt and len(match_txt) > 5:
                    line.text = f"<font color='#ffff00'>{txt}</font>"
                else:
                    line.text = f"<font color='#ffff00'>{txt}</font>\\N{match_txt}"
                    last_match_txt = match_txt
            else:
                line.text = txt

            progress.advance(task_id, 1)

        output_filename = f"{series_folder}_{tag}_Dual.srt"
        s_en.save(os.path.join(final_out_path, output_filename), encoding="utf-8")
        progress.update(task_id, description=f"[green]✓ {tag}", completed=len(s_en))
        logger.info(f"Generado: {output_filename}")

    except Exception as e:
        progress.update(task_id, description=f"[red]Error: {str(e)[:10]}...", completed=100)
        logger.error(f"Excepción en {f_en}: {e}")

def process_season_logic(clean_name, show_id, season, max_threads):
    console.rule(f"[bold]Procesando Temporada {season}[/bold]")
    logger.info(f"--- INICIO TEMPORADA {season} ---")
    clean_workspace()

    with console.status(f"[bold yellow]Descargando packs Temporada {season}..."):
        ok_en = download_zip(clean_name, show_id, season, "en")
        ok_es = download_zip(clean_name, show_id, season, "es")

    if not ok_en:
        console.print(f"[red]✗ Temporada {season}: Pack Inglés no encontrado.[/red]")
        logger.warning(f"T{season}: Pack EN no encontrado. Saltando.")
        return False

    # Setup carpetas
    series_folder = clean_name.replace(" ", "_")
    final_out_path = os.path.join(OUT_BASE_DIR, series_folder, f"Season_{season}")
    os.makedirs(final_out_path, exist_ok=True)

    en_dir = os.path.join(WORK_DIR, "en")
    es_dir = os.path.join(WORK_DIR, "es")
    en_files = sorted([f for f in os.listdir(en_dir) if f.lower().endswith(('.srt', '.sub'))])

    if not en_files: return False

    console.print(f"[cyan]---> Procesando {len(en_files)} eps con {max_threads} hilos <---[/cyan]")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.fields[filename]}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("{task.description}"),
    )

    with Live(progress, refresh_per_second=10):
        futures = []
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            for f_en in en_files:
                task_id = progress.add_task("Wait...", filename=f_en[:15]+"..", total=100)
                future = executor.submit(
                    process_single_episode,
                    f_en, en_dir, es_dir, WORK_DIR, final_out_path, series_folder, progress, task_id
                )
                futures.append(future)
            for _ in as_completed(futures): pass

    save_cache()
    return True

def main():
    console.print(Panel("[bold white on blue] SUBSYNC V21: ANTI-ECHO UPDATED [/bold white on blue]"))
    logger.info("Sesión iniciada")

    query = questionary.text("Serie a buscar:").ask()
    if not query: return

    results = get_search_results(query)
    if not results:
        console.print("[red]No se encontraron resultados.[/red]")
        return

    d_map = {f"{r['display']} [ID:{r['id']}]": r for r in results}
    choice = questionary.select("Selecciona:", choices=list(d_map.keys())).ask()
    selected = d_map[choice]

    season_input = questionary.text("Temporadas (ej: '1-N'):").ask()
    seasons = parse_seasons(season_input)

    cpu_cores = os.cpu_count() or 4
    try:
        t_input = questionary.text(f"Hilos (Detectados {cpu_cores}):", default=str(cpu_cores)).ask()
        max_threads = int(t_input)
    except: max_threads = 4

    current_season = 1
    is_infinite = (seasons is None)

    while True:
        if not is_infinite:
            if not seasons: break
            s_num = seasons.pop(0)
        else: s_num = current_season

        success = process_season_logic(selected['clean_name'], selected['id'], s_num, max_threads)

        if is_infinite and not success:
            console.print(f"[bold red]Fin del trayecto en T{s_num}.[/bold red]")
            break

        if is_infinite:
            current_season += 1
            if current_season > 50: break

    console.print(Panel(f"[bold green]¡Listo![/bold green]\nArchivos en: [u]{OUT_BASE_DIR}/{selected['clean_name'].replace(' ','_')}/[/u]"))

if __name__ == "__main__":
    main()
