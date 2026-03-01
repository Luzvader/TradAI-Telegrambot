"""
Sistema de autenticación para el dashboard web.

Genera códigos de un solo uso desde Telegram (/web) y gestiona sesiones
de 24 horas mediante cookies httpOnly.
Incluye rate-limiting por IP contra fuerza bruta.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)

# ── Constantes ───────────────────────────────────────────────

CODE_LENGTH = 6  # Dígitos del código de acceso
CODE_TTL_MINUTES = 5  # El código expira en 5 minutos
SESSION_TTL_HOURS = 24  # La sesión dura 24 horas
SESSION_COOKIE = "tradai_session"

# Rate-limiting
MAX_LOGIN_ATTEMPTS = 5  # Máximo intentos por ventana
LOCKOUT_MINUTES = 15  # Bloqueo tras exceder intentos


# ── Modelos ──────────────────────────────────────────────────


@dataclass
class AccessCode:
    """Código de acceso de un solo uso."""

    code: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    used: bool = False

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.created_at + timedelta(minutes=CODE_TTL_MINUTES)

    @property
    def is_valid(self) -> bool:
        return not self.used and not self.is_expired


@dataclass
class Session:
    """Sesión autenticada (24h)."""

    token: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.created_at + timedelta(hours=SESSION_TTL_HOURS)

    @property
    def expires_at(self) -> datetime:
        return self.created_at + timedelta(hours=SESSION_TTL_HOURS)


# ── Gestor de autenticación (singleton) ──────────────────────


class AuthManager:
    """Almacén en memoria para códigos de acceso, sesiones y rate-limiting."""

    def __init__(self) -> None:
        self._codes: dict[str, AccessCode] = {}
        self._sessions: dict[str, Session] = {}
        # Rate-limiting por IP: {ip: [(timestamp, ...)]}
        self._login_attempts: dict[str, list[datetime]] = defaultdict(list)

    # ── Códigos ──────────────────────────────────────────────

    def generate_code(self) -> str:
        """Genera un nuevo código numérico de un solo uso.

        Invalida cualquier código anterior no utilizado.
        """
        # Invalidar códigos previos
        for c in self._codes.values():
            if not c.used:
                c.used = True

        code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
        self._codes[code] = AccessCode(code=code)
        logger.info("🔑 Nuevo código de acceso web generado")
        return code

    def validate_code(self, code: str) -> bool:
        """Valida y consume un código. Devuelve True si era válido."""
        ac = self._codes.get(code)
        if ac and ac.is_valid:
            ac.used = True
            logger.info("✅ Código de acceso web utilizado correctamente")
            self._cleanup_codes()
            return True
        logger.warning(f"❌ Intento de acceso web con código inválido: {code}")
        self._cleanup_codes()
        return False

    # ── Sesiones ─────────────────────────────────────────────

    def create_session(self) -> Session:
        """Crea una nueva sesión de 24h y devuelve el token."""
        token = secrets.token_urlsafe(32)
        session = Session(token=token)
        self._sessions[token] = session
        logger.info("🔐 Nueva sesión web creada (expira en 24h)")
        self._cleanup_sessions()
        return session

    def validate_session(self, token: str | None) -> bool:
        """Comprueba si un token de sesión es válido."""
        if not token:
            return False
        session = self._sessions.get(token)
        if session and not session.is_expired:
            return True
        # Eliminar sesión expirada
        if session:
            del self._sessions[token]
        return False

    def revoke_session(self, token: str) -> None:
        """Revoca una sesión activa."""
        self._sessions.pop(token, None)

    # ── Rate-limiting ─────────────────────────────────────────

    def record_login_attempt(self, ip: str) -> None:
        """Registra un intento de login fallido desde una IP."""
        now = datetime.now(UTC)
        self._login_attempts[ip].append(now)
        # Solo guardar intentos recientes
        cutoff = now - timedelta(minutes=LOCKOUT_MINUTES)
        self._login_attempts[ip] = [
            t for t in self._login_attempts[ip] if t > cutoff
        ]

    def is_ip_blocked(self, ip: str) -> bool:
        """Comprueba si una IP está bloqueada por demasiados intentos."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=LOCKOUT_MINUTES)
        attempts = [t for t in self._login_attempts[ip] if t > cutoff]
        self._login_attempts[ip] = attempts
        return len(attempts) >= MAX_LOGIN_ATTEMPTS

    def clear_login_attempts(self, ip: str) -> None:
        """Limpia intentos tras login exitoso."""
        self._login_attempts.pop(ip, None)

    def get_remaining_lockout(self, ip: str) -> int:
        """Devuelve minutos restantes de bloqueo (0 si no bloqueado)."""
        if not self.is_ip_blocked(ip):
            return 0
        oldest = min(self._login_attempts[ip])
        unlock_at = oldest + timedelta(minutes=LOCKOUT_MINUTES)
        remaining = (unlock_at - datetime.now(UTC)).total_seconds() / 60
        return max(1, int(remaining) + 1)

    # ── Limpieza ─────────────────────────────────────────────

    def _cleanup_codes(self) -> None:
        expired = [k for k, v in self._codes.items() if not v.is_valid]
        for k in expired:
            del self._codes[k]

    def _cleanup_sessions(self) -> None:
        expired = [k for k, v in self._sessions.items() if v.is_expired]
        for k in expired:
            del self._sessions[k]

    @property
    def active_sessions_count(self) -> int:
        self._cleanup_sessions()
        return len(self._sessions)


# Instancia global
auth_manager = AuthManager()
