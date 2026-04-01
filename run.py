from pathlib import Path

import uvicorn

CERT_DIR = Path(__file__).parent / "certs"
CERT_FILE = CERT_DIR / "cert.pem"
KEY_FILE = CERT_DIR / "key.pem"


def generate_self_signed_cert():
    """Generate a self-signed certificate using pure Python (cryptography lib)."""
    CERT_DIR.mkdir(exist_ok=True)

    if CERT_FILE.exists() and KEY_FILE.exists():
        return

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime

    print("Generating self-signed SSL certificate...")

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "yugipy-local"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )

    KEY_FILE.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Certificate saved to {CERT_DIR}")


import logging

class QuietRouteFilter(logging.Filter):
    """Suppress noisy access log lines for high-frequency endpoints."""
    SUPPRESSED = ("/api/ocr-preview",)

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(route in msg for route in self.SUPPRESSED)

logging.getLogger("uvicorn.access").addFilter(QuietRouteFilter())


if __name__ == "__main__":
    generate_self_signed_cert()

    print()
    print("=" * 50)
    print("  YugiPy server running on HTTPS")
    print("  Open from your phone:")
    print("  https://<your-pc-ip>:8000")
    print()
    print("  NOTE: The browser will warn about the")
    print("  self-signed certificate. Tap 'Advanced'")
    print("  then 'Proceed' to continue.")
    print("=" * 50)
    print()

    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        ssl_keyfile=str(KEY_FILE),
        ssl_certfile=str(CERT_FILE),
    )
