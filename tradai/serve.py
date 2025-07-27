from __future__ import annotations
import datetime
from pathlib import Path
import os
import logging
from typing import Optional
import ssl

import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI

from .web import app
from .options import load_options

# Configuración de logging consistente con otros módulos
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuración predeterminada
DEFAULT_CERT_DIR = Path.home() / ".tradai_ssl"
DEFAULT_CERT_FILE = DEFAULT_CERT_DIR / "cert.pem"
DEFAULT_KEY_FILE = DEFAULT_CERT_DIR / "key.pem"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def generate_cert(cert_file: Path = DEFAULT_CERT_FILE, key_file: Path = DEFAULT_KEY_FILE) -> None:
    """Genera un certificado SSL autofirmado y clave privada si no existen.

    Args:
        cert_file (Path): Ruta al archivo de certificado (default: ~/.tradai_ssl/cert.pem).
        key_file (Path): Ruta al archivo de clave privada (default: ~/.tradai_ssl/key.pem).

    Raises:
        RuntimeError: Si falla la generación o escritura de los certificados.
    """
    if cert_file.exists() and key_file.exists():
        try:
            with cert_file.open("rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())
                not_after = cert.not_valid_after
                if not_after > datetime.datetime.utcnow():
                    logger.info(f"Certificado existente válido hasta {not_after}")
                    return
                logger.info(f"Certificado expirado ({not_after}); regenerando")
        except Exception as e:
            logger.warning(f"Error al validar certificado existente: {e}; regenerando")

    try:
        cert_dir = cert_file.parent
        cert_dir.mkdir(parents=True, exist_ok=True)

        # Generar clave privada
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        # Generar certificado
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )

        # Escribir clave privada con permisos seguros
        with key_file.open("wb") as f:
            f.write(
                key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        os.chmod(key_file, 0o600)  # Permisos solo lectura/escritura para propietario
        logger.info(f"Clave privada generada en {key_file}")

        # Escribir certificado
        with cert_file.open("wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        os.chmod(cert_file, 0o644)  # Permisos lectura para todos, escritura para propietario
        logger.info(f"Certificado generado en {cert_file}")

    except Exception as e:
        logger.error(f"Error al generar certificado SSL: {e}")
        raise RuntimeError(f"Failed to generate SSL certificate: {e}")


def main(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    cert_dir: Path = DEFAULT_CERT_DIR,
    http_only: bool = False,
) -> None:
    """Inicia el servidor web FastAPI con soporte para HTTP o HTTPS.

    Args:
        host (str): Dirección del servidor (default: "127.0.0.1").
        port (int): Puerto del servidor (default: 8000).
        cert_dir (Path): Directorio para certificados SSL (default: ~/.tradai_ssl).
        http_only (bool): Si True, usa HTTP en lugar de HTTPS (default: False).

    Raises:
        RuntimeError: Si falla la generación de certificados o el inicio del servidor.
        ValueError: Si app no es una instancia válida de FastAPI.
    """
    if not isinstance(app, FastAPI):
        logger.error("La aplicación 'app' no es una instancia válida de FastAPI")
        raise ValueError("Invalid FastAPI application")

    # Cargar configuraciones desde options.py
    opts = load_options()
    http_only = http_only or bool(os.getenv("TRADAI_HTTP") or opts.get("http_only", False))
    host = opts.get("server_host", host)
    port = int(opts.get("server_port", port))
    cert_file = Path(opts.get("cert_file", cert_dir / "cert.pem"))
    key_file = Path(opts.get("key_file", cert_dir / "key.pem"))

    try:
        if not http_only:
            generate_cert(cert_file=cert_file, key_file=key_file)
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(certfile=str(cert_file), keyfile=str(key_file))
            ssl_args = {"ssl_context": ssl_context}
        else:
            ssl_args = {}
            logger.info("Iniciando servidor en modo HTTP (sin SSL)")

        logger.info(f"Iniciando servidor en {host}:{port}")
        uvicorn.run(
            app,
            host=host,
            port=port,
            **ssl_args,
        )
    except Exception as e:
        logger.error(f"Error al iniciar el servidor: {e}")
        raise RuntimeError(f"Failed to start server: {e}")


if __name__ == "__main__":  # pragma: no cover - ejecución manual
    main()
