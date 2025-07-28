from __future__ import annotations
from pathlib import Path
from typing import Dict
import xml.etree.ElementTree as ET
from datetime import datetime
import logging
import threading
import os

# Configuración de logging consistente con otros módulos
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
OPTIONS_FILE = ROOT_DIR / "options.xml"
FILE_LOCK = threading.Lock()

def get_openai_api_key(options: Dict[str, str]) -> str:
    """Get the OpenAI API key from options or environment variable.

    Accepts ``openai_api_key`` or ``openai_key`` as valid keys.
    """
    if "openai_api_key" in options:
        return options["openai_api_key"]
    if "openai_key" in options:
        return options["openai_key"]
    
    # Fallback to environment variable if not found in options
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        logger.info("Usando openai_api_key de variable de entorno")
        return api_key
    
    # If not found, raise an error
    logger.error("No se encontró 'openai_api_key' o 'openai_key' en XML ni en variable de entorno")
    raise ValueError("Missing OpenAI API key in configuration")

def load_options() -> Dict[str, str]:
    """Load options from ``OPTIONS_FILE`` returning a mapping.

    Returns:
        Dict[str, str]: Dictionary of configuration options (key: value).
        Empty dict if file doesn't exist, is malformed, or missing mandatory keys.

    Notes:
        - Validates that the XML root is 'options' and contains
          either 'openai_api_key' or 'openai_key'.
        - Falls back to environment variable OPENAI_API_KEY if not in XML.
    """
    if not OPTIONS_FILE.exists():
        logger.warning(f"Archivo de opciones {OPTIONS_FILE} no encontrado")
        return {}

    try:
        tree = ET.parse(OPTIONS_FILE)
        root = tree.getroot()
        
        if root.tag != "options":
            logger.error(f"Etiqueta raíz XML debe ser 'options', encontrada: {root.tag}")
            raise ValueError("XML root tag must be 'options'")

        options = {}
        for option in root.findall("option"):
            key_elem = option.find("key")
            value_elem = option.find("value")
            if key_elem is None or value_elem is None or key_elem.text is None:
                logger.error(f"Estructura XML inválida en opción: {ET.tostring(option, encoding='unicode')}")
                continue
            key = key_elem.text.strip()
            if not key:
                logger.error("Clave XML vacía encontrada")
                continue
            options[key] = value_elem.text or ""

        # Validate and return API key
        get_openai_api_key(options)
        logger.info(f"Opciones cargadas desde {OPTIONS_FILE}: {list(options.keys())}")
        return options

    except ET.ParseError as e:
        logger.error(f"Error al parsear {OPTIONS_FILE}: {e}")
        return {}
    except ValueError as e:
        logger.error(f"Error de validación: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error inesperado al cargar opciones de {OPTIONS_FILE}: {e}")
        return {}

def save_options(opts: Dict[str, str]) -> None:
    """Persist ``opts`` to ``OPTIONS_FILE`` in XML format.

    Args:
        opts (Dict[str, str]): Dictionary of configuration options to save.

    Raises:
        ValueError: If any key or value is invalid (e.g., empty or non-string).
    """
    # Validate opts before saving
    for key, value in opts.items():
        if not isinstance(key, str) or not isinstance(value, str):
            logger.error(f"Clave o valor no es una cadena de texto. Clave: {key}, Valor: {value}")
            raise ValueError(f"Clave o valor no es una cadena de texto. Clave: {key}, Valor: {value}")

    root = ET.Element("options")

    # Add current timestamp and version as metadata
    metadata = ET.SubElement(root, "metadata")
    version = ET.SubElement(metadata, "version")
    version.text = "1.0"
    created_at = ET.SubElement(metadata, "created_at")
    created_at.text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Add options to XML
    for key, value in opts.items():
        option = ET.SubElement(root, "option")
        key_elem = ET.SubElement(option, "key")
        key_elem.text = key
        value_elem = ET.SubElement(option, "value")
        value_elem.text = value

    try:
        # Writing with file lock to prevent concurrent access issues
        with FILE_LOCK:
            tree = ET.ElementTree(root)
            tree.write(OPTIONS_FILE, encoding="utf-8", xml_declaration=True)
            logger.info(f"Opciones guardadas exitosamente en {OPTIONS_FILE}")
    except Exception as e:
        logger.error(f"Error al guardar las opciones: {e}")
        raise RuntimeError(f"Error al guardar las opciones: {e}")
