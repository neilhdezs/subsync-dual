from rich.console import Console, Group
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.live import Live
from rich.panel import Panel
from collections import deque
from threading import Lock

# Creamos la consola "Rich", que permite texto con colores y formato avanzado.
console = Console()

# --- CLASE: LogManager ---
# Esta clase se encarga de gestionar los mensajes de log que se muestran
# en el panel inferior de la interfaz.
class LogManager:
    def __init__(self, max_len=10):
        # deque es una lista optimizada que, al llenarse, borra automáticamente el más viejo.
        # Aquí guardaremos solo los últimos 10-12 mensajes para no saturar la pantalla.
        self.logs = deque(maxlen=max_len)
        
        # Lock para evitar que dos hilos escriban a la vez y corrompan la lista.
        self.lock = Lock()
    
    def add(self, msg):
        """Añade un mensaje nuevo a la lista de logs de forma segura (con lock)."""
        with self.lock:
            self.logs.append(msg)
    
    def get_text(self):
        """Devuelve todo el texto acumulado unido por saltos de línea (\n)."""
        with self.lock:
            return "\n".join(self.logs)

# --- FUNCIÓN: get_dynamic_layout ---
# Esta función construye lo que se ve en pantalla en cada refresco.
def get_dynamic_layout(progress, log_mgr):
    """
    Crea un GRUPO visual que contiene:
    1. La barra de progreso (arriba).
    2. El panel de logs (abajo).
    """
    return Group(
        progress,
        Panel(log_mgr.get_text(), title="Real-time Logs", height=14, border_style="blue")
    )

# --- CONFIGURACIÓN DE PROGRESO ---
# Configuración de las barras de carga de Rich.
# SpinnerColumn: El circulito que gira.
# TextColumn: El nombre del archivo.
# BarColumn: La barra de porcentaje [====....]
def create_progress():
    return Progress(
        SpinnerColumn(), 
        TextColumn("[bold blue]{task.fields[filename]}"), 
        BarColumn(), 
        TextColumn("{task.description}")
    )
