from pathlib import Path

import uvicorn

CERT_DIR = Path(__file__).parent / "certs"
CERT_FILE = CERT_DIR / "cert.pem"
KEY_FILE = CERT_DIR / "key.pem"


def _get_local_ips() -> list[str]:
    """Return all local IPv4 addresses (excluding loopback)."""
    import socket
    ips = []
    try:
        # Primary LAN IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    # Also try all interfaces
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and ip != "127.0.0.1":
                ips.append(ip)
    except Exception:
        pass
    return ips


def _cert_needs_regen() -> bool:
    """Check if the existing cert's SANs cover localhost + current local IPs."""
    if not CERT_FILE.exists() or not KEY_FILE.exists():
        return True
    try:
        from cryptography import x509 as x509mod
        cert = x509mod.load_pem_x509_certificate(CERT_FILE.read_bytes())
        ext = cert.extensions.get_extension_for_class(x509mod.SubjectAlternativeName)
        san_dns = set(ext.value.get_values_for_type(x509mod.DNSName))
        san_ips = {str(ip) for ip in ext.value.get_values_for_type(x509mod.IPAddress)}
        needed_ips = {"127.0.0.1"} | set(_get_local_ips())
        return not ({"localhost"} <= san_dns and needed_ips <= san_ips)
    except Exception:
        return True


def generate_self_signed_cert():
    """Generate a self-signed certificate with SANs for localhost + all local IPs."""
    CERT_DIR.mkdir(exist_ok=True)

    if not _cert_needs_regen():
        return

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime
    import ipaddress

    local_ips = _get_local_ips()
    print(f"Generating self-signed SSL certificate (IPs: 127.0.0.1, {', '.join(local_ips)})...")

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "yugipy-local"),
    ])

    san_names = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    for ip in local_ips:
        san_names.append(x509.IPAddress(ipaddress.ip_address(ip)))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(san_names), critical=False)
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
    SUPPRESSED = ("/api/ocr-preview", "/api/extension/status")

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
