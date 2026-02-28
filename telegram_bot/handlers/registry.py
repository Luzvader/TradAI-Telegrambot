"""Registro centralizado de comandos del bot de Telegram.

Cada módulo handler define una lista ``COMMANDS`` de :class:`CommandInfo`.
El paquete ``handlers/__init__.py`` los recopila en ``ALL_COMMANDS`` y
``bot.py`` los usa para registrar los handlers y el menú de Telegram.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class CommandInfo:
    """Metadatos de un comando del bot."""

    name: str
    handler: Callable
    description: str
