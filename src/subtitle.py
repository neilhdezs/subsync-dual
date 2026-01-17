import os
import re
import pysubs2
from src.config import logger
from src.api import translate_batch_native

def process_episode(f_en, en_dir, out_dir, series_name, progress, task_id, log_mgr):
    """
    Procesa un único capítulo: Carga, Traduce por bloques, Guarda.
    Se ejecuta en un hilo separado por cada capítulo.
    """
    try:
        log_mgr.add(f"[cyan]Iniciando: {f_en}[/cyan]")
        
        # Ruta completa del archivo en inglés
        path_en = os.path.join(en_dir, f_en)
        
        # Intentamos cargar el archivo .srt.
        # A veces vienen en codificación utf-8 (moderno) y otras en latin-1 (antiguo).
        try: subs = pysubs2.load(path_en, encoding="utf-8")
        except: 
            try: subs = pysubs2.load(path_en, encoding="latin-1")
            except: return # Si falla todo, nos rendimos con este archivo.

        # Extraemos solo el texto limpio (quitando cosas raras como \N que es salto de línea)
        clean_lines = [line.text.replace("\\N", " ").strip() for line in subs]
        
        # Preparamos la barra de progreso de este archivo
        progress.update(task_id, description="[cyan]Traduciendo (JSON Nativo)...", total=len(subs))
        
        # === BUCLE DE TRADUCCIÓN POR LOTES ===
        # En vez de ir 1 a 1, vamos de 50 en 50 para ser más rápidos.
        BATCH_SIZE = 50
        all_translations = []
        
        for i in range(0, len(clean_lines), BATCH_SIZE):
            # Cogemos un trozo de 50 líneas
            batch = clean_lines[i : i + BATCH_SIZE]
            
            # Escribimos en el log cada 5 bloques (para no saturar visualmente)
            if i % (BATCH_SIZE * 5) == 0:
                 log_mgr.add(f"[dim]Proc {f_en[:10]}... Batch {i//BATCH_SIZE}[/dim]")
                 
            # ¡MAGIA! Llamamos a la API para traducir esas 50 líneas.
            translated_batch = translate_batch_native(batch)
            all_translations.extend(translated_batch)
            
            # Avanzamos la barra de progreso
            progress.advance(task_id, len(batch))

        # === MONTAJE DEL DUAL DUAL ===
        # Ahora unimos el Inglés original (arriba) con el Español traducido (abajo).
        for i, line in enumerate(subs):
            original = clean_lines[i]
            if not original: continue # Si la línea estaba vacía, pasamos.
            
            # Recuperamos la traducción correspondiente (o avisamos si falta).
            spanish = all_translations[i] if i < len(all_translations) else "[Falta]"
            
            # Formato SRS Dual: Original en amarillo + Salto de línea + Traducción en blanco.
            line.text = f"<font color='#ffff00'>{original}</font>\\N{spanish}"

        # === GUARDADO ===
        # Detectamos el número de episodio (S04E07) del nombre del archivo para nombrar el nuevo.
        tag_match = re.search(r'(S\d+E\d+|\d+x\d+)', f_en, re.IGNORECASE)
        tag = tag_match.group(1).upper() if tag_match else f_en[:10]
        
        # Guardamos el archivo final.
        subs.save(os.path.join(out_dir, f"{series_name}_{tag}_Dual.srt"), encoding="utf-8")
        
        # Marcamos la tarea como completada en verde.
        progress.update(task_id, description=f"[green]✓ {tag}")
        log_mgr.add(f"[bold green]Terminado: {tag}[/bold green]")

    except Exception as e:
        # Si algo explota, lo apuntamos en el log rojo.
        logger.error(f"Error {f_en}: {e}")
        progress.update(task_id, description="[red]Error")
        log_mgr.add(f"[bold red]ERROR {f_en}: {e}[/bold red]")
