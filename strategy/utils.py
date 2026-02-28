"""
Utilidades compartidas para las estrategias de scoring.
"""


def clamp(score: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    """Limita un score al rango [min_val, max_val]."""
    return max(min_val, min(max_val, score))
