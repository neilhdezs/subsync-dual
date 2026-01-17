import json
import time
import difflib
import google.generativeai as genai
import warnings

# Elimina las alertas de "deprecated" de google.generativeai
warnings.simplefilter('ignore')

# Importaciones propias
from src.config import GOOGLE_API_KEY, logger, api_lock
from src.utils import TRANSLATION_CACHE, cache_lock

# --- CONFIGURACIÓN DE IA ---
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    
    # Configuración para que la IA responda SIEMPRE en formato JSON
    generation_config = genai.types.GenerationConfig(
        temperature=0.1, # Creatividad baja (0.1) para que sea literal y no invente.
        response_mime_type="application/json" 
    )
    # Modelo Gemini 2.5 Flash Lite (Versión de pago barata y rápida)
    model = genai.GenerativeModel('gemini-2.5-flash-lite', generation_config=generation_config)
else:
    model = None

# --- FUNCIÓN PRINCIPAL DE TRADUCCIÓN ---
def translate_batch_native(lines):
    """
    Traduce una lista de frases (batch) de golpe usando IA.
    Envía un bloque JSON y espera un bloque JSON de vuelta.
    """
    # 1. Separar lo que ya tenemos en CACHÉ de lo que hay que pedir nuevo.
    indices_to_fetch = []
    texts_to_fetch = []
    results = [""] * len(lines)
    
    for i, text in enumerate(lines):
        txt_clean = text.strip()
        if not txt_clean: continue # Si está vacío, saltar
        
        # Bloqueamos el caché para leer (seguridad multihilo)
        with cache_lock:
            if txt_clean in TRANSLATION_CACHE:
                # ¡Ya lo tenemos! No gastamos dinero en la API.
                results[i] = TRANSLATION_CACHE[txt_clean]
            else:
                # Hay que pedirlo. Guardamos posición y texto.
                indices_to_fetch.append(i)
                texts_to_fetch.append(txt_clean)
    
    # Si todo estaba en caché, retornamos directo.
    if not texts_to_fetch: return results

    # 2. Construir el Prompt (Las instrucciones para la IA)
    # Le decimos explícitamente qué queremos: JSON, Español Neutro, No repetir inglés.
    prompt = f"""
    ROLE: You are an expert subtitler and translator specializing in American English to Neutral Spanish (Latin American) localization.
    TASK: Translate the provided list of English subtitle lines into natural, conversational Neutral Spanish.

    INPUT LIST:
    {json.dumps(texts_to_fetch)}

    STRICT RULES:
    1. OUTPUT FORMAT: Return ONLY a JSON object with a single key "translations" containing the list of translated strings.
    2. ORDER: The order of the output list MUST match the input list exactly (Index 0 to {len(texts_to_fetch)-1}).
    3. NO ECHO: NEVER copy the English text. If you cannot translate it, provide a best guess based on context. 
       - Exception: Proper names (Joey, Ross, Chandler) should remain kept, but the surrounding text MUST be Spanish.
    4. NO HALLUCINATIONS: Do not add extra lines or combine lines.
    5. TONE: Informal, as used in TV shows. "You" -> "Tú" (unless formal context implies "Usted", but default to "Tú").
    
    CRITICAL:
    - If the input is "Yeah." -> Output "Sí." (NOT "Yeah.")
    - If the input is "Oh my god." -> Output "Dios mío." (NOT "Oh my god.")
    """

    translations = []
    
    # 3. Intentar la traducción hasta 3 veces por si falla la red
    for attempt in range(3):
        try:
            # OPTIMIZACIÓN: Como usamos la versión de pago, NO usamos sleeps ni locks.
            # Pedimos a Gemini que genere el contenido.
            response = model.generate_content(prompt)
            
            # Convertimos el texto recibido (string) a objeto Python (dict/list)
            data = json.loads(response.text)
            candidates = data.get("translations", [])
            
            # VERIFICACIÓN DE SEGURIDAD 1: Longitud
            # Si enviamos 50 frases, esperaríamos 50 traduccdiones.
            if len(candidates) != len(texts_to_fetch):
                logger.warning(f"Descuadre JSON (Esperado {len(texts_to_fetch)}, Recibido {len(candidates)}). Reintentando...")
                continue
            
            # VERIFICACIÓN DE SEGURIDAD 2: "Traducción Vaga"
            # A veces la IA se cansa y devuelve el texto en inglés. Detectamos si se repite mucho.
            is_lazy = False
            if len(candidates) > 0:
                # Comparamos las 3 primeras frases originales con las traducidas.
                english_snippet = " ".join(texts_to_fetch[:3]).lower()
                spanish_snippet = " ".join(candidates[:3]).lower()
                # difflib nos dice cuán parecidos son los textos (0.0 a 1.0)
                ratio = difflib.SequenceMatcher(None, english_snippet, spanish_snippet).ratio()
                if ratio > 0.8: is_lazy = True # Si son 80% iguales, es que no tradujo.

            if is_lazy:
                logger.warning("Detectada respuesta vaga (inglés repetido). Forzando reintento...")
                # Le gritamos un poco en el prompt para el siguiente intento.
                prompt += "\n\nCRITICAL ERROR: You returned English text. YOU MUST TRANSLATE TO SPANISH."
                continue
 
            # Si pasamos las verificaciones, es un éxito.
            translations = candidates
            break 

        except Exception as e:
            # Manejo de Errores de API
            if "429" in str(e): 
                # Error 429 = "Has superado el límite de velocidad". Esperamos 20s.
                logger.warning("Quota limit (429). Waiting 20s...")
                time.sleep(20)
                continue
            logger.error(f"Error Batch JSON: {e}")
            # Si es otro error, reintentamos el loop.
            
    # 4. Asignar los resultados nuevos a la lista final
    # Si tras 3 intentos falló todo, ponemos "[ERROR API]" para no romper el programa.
    if not translations:
        translations = ["[ERROR API]"] * len(texts_to_fetch)
        # Último recurso: intentar traducir una por una (muy lento, solo para pocos fallos)
        if len(texts_to_fetch) < 5: 
             translations = [translate_single_emergency(t) for t in texts_to_fetch]

    # Guardar en memoria caché para futuras ejecuciones
    for i, idx_global in enumerate(indices_to_fetch):
        if i < len(translations):
            final_txt = translations[i]
            results[idx_global] = final_txt
            if "[ERROR" not in final_txt:
                with cache_lock: TRANSLATION_CACHE[texts_to_fetch[i]] = final_txt

    return results

def translate_single_emergency(text):
    """
    Función de emergencia: Traducción simple 1 a 1 sin JSON.
    Se usa cuando el modo batch falla catastróficamente.
    """
    try:
        # Desactivamos JSON mode para este fallback simple
        model_txt = genai.GenerativeModel('gemini-2.5-flash-lite') 
        res = model_txt.generate_content(f"¿Cómo se dice '{text}' en español? Solo la respuesta.")
        return res.text.strip()
    except:
        return text
