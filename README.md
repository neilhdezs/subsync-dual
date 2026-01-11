# SubSync Dual

**Herramienta para descargar, sincronizar y fusionar subtítulos en Inglés y Español.**

![Version](https://img.shields.io/badge/version-0.1.0-blue) ![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![License](https://img.shields.io/badge/License-MIT-green)

Este script permite automatizar el proceso de obtención de subtítulos para series. Descarga los archivos de TVSubtitles, sincroniza el audio usando `alass` y genera un único archivo `.srt` con ambos idiomas (Inglés arriba, Español abajo).

## Características

* **Descarga Automática:** Busca y descarga temporadas completas.
* **Sincronización:** Alinea los tiempos del subtítulo en español basándose en el inglés usando `alass`.
* **Formato Dual:**
    * Inglés: Blanco (Superior).
    * Español: Amarillo (Inferior).
* **Traducción Automática:** Si no existe subtítulo en español, utiliza Google Translate para generarlo.
* **Procesamiento Paralelo:** Permite procesar múltiples episodios simultáneamente.

## Requisitos

1.  **Python 3.10** o superior.
2.  **`alass`:** Binario necesario para la sincronización de tiempos.
    * *Arch Linux:* `sudo pacman -S alass`
    * *Otros:* Descargar desde el repositorio oficial de `kaegi/alass` y añadir al PATH.

## Instalación

1.  Clonar el repositorio:
    ~~~bash
    git clone https://github.com/tu-usuario/subsync-dual.git
    cd subsync-dual
    ~~~

2.  Instalar dependencias (usando `pip` o `uv`):
    ~~~bash
    pip install -r requirements.txt
    ~~~

## Uso

Ejecutar el script principal:

~~~bash
python subsync.py
~~~

El programa solicitará:
1.  Nombre de la serie.
2.  Temporadas a descargar (ej: `1`, `1-5`, `1-N`).
3.  Número de hilos de procesamiento (núcleos de CPU a utilizar).

## Estructura de Salida

Los archivos generados se guardan en la carpeta `Final_Dual_Subs`:

~~~text
Final_Dual_Subs/
└── Nombre_Serie/
    ├── Season_1/
    │   ├── Serie - S01E01 [Dual].srt
    │   └── ...
~~~

## Notas

* Se genera un archivo `subsync.log` con el registro de la ejecución.
* La carpeta `workspace` se utiliza para archivos temporales y se limpia en cada uso.

## Licencia

Este proyecto está bajo la Licencia MIT.
