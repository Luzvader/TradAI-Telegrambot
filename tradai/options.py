from __future__ import annotations

from pathlib import Path
from typing import Dict
import xml.etree.ElementTree as ET

ROOT_DIR = Path(__file__).resolve().parent.parent
OPTIONS_FILE = ROOT_DIR / "options.xml"


def load_options() -> Dict[str, str]:
    """Load options from ``OPTIONS_FILE`` returning a mapping."""
    if not OPTIONS_FILE.exists():
        return {}
    try:
        tree = ET.parse(OPTIONS_FILE)
        root = tree.getroot()
        return {child.tag: child.text or "" for child in root}
    except Exception:
        return {}


def save_options(opts: Dict[str, str]) -> None:
    """Persist ``opts`` to ``OPTIONS_FILE`` in XML format."""
    root = ET.Element("options")
    for key, value in opts.items():
        el = ET.SubElement(root, key)
        el.text = value
    tree = ET.ElementTree(root)
    tree.write(OPTIONS_FILE, encoding="utf-8", xml_declaration=True)
