"""
TLS/SSL certificate analysis utilities for JAGUAR.

Provides certificate validation, expiration checking, and
protocol/cipher analysis used by the security analyzer.
"""

from __future__ import annotations

import logging
import socket
import ssl
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("jaguar.crypto")


async def get_certificate_info(hostname: str, port: int = 443) -> dict[str, Any]:
    """
    Retrieve TLS certificate information for a hostname.

    This performs a direct SSL connection to capture certificate details
    that may not be available through aiohttp's response object.
    """
    info: dict[str, Any] = {
        "valid": False,
        "hostname_match": False,
        "expired": False,
        "days_until_expiry": None,
        "issuer": {},
        "subject": {},
        "serial_number": "",
        "not_before": "",
        "not_after": "",
        "san": [],
        "protocol": "",
        "cipher": "",
        "key_size": None,
        "signature_algorithm": "",
    }

    try:
        context = ssl.create_default_context()
        conn = context.wrap_socket(
            socket.socket(socket.AF_INET),
            server_hostname=hostname,
        )
        conn.settimeout(10)
        conn.connect((hostname, port))

        cert = conn.getpeercert()
        conn.getpeercert(binary_form=True)

        if cert:
            info["valid"] = True
            info["hostname_match"] = True

            # Subject and issuer
            info["subject"] = _parse_cert_field(cert.get("subject", ()))  # type: ignore
            info["issuer"] = _parse_cert_field(cert.get("issuer", ()))  # type: ignore

            # Dates
            not_before = cert.get("notBefore", "")
            not_after = cert.get("notAfter", "")
            info["not_before"] = not_before
            info["not_after"] = not_after

            # Expiration check
            if not_after:
                expiry = _parse_cert_date(not_after)  # type: ignore
                if expiry:
                    now = datetime.now(UTC)
                    delta = expiry - now
                    info["days_until_expiry"] = delta.days
                    info["expired"] = delta.days < 0

            # Serial number
            info["serial_number"] = cert.get("serialNumber", "")

            # Subject Alternative Names
            san = cert.get("subjectAltName", ())
            info["san"] = [entry[1] for entry in san]

        # Connection info
        info["protocol"] = conn.version() or ""
        cipher_info = conn.cipher()
        if cipher_info:
            info["cipher"] = cipher_info[0]
            info["key_size"] = cipher_info[2]

        conn.close()

    except ssl.SSLCertVerificationError as e:
        logger.debug("Certificate verification failed for %s: %s", hostname, e)
        info["valid"] = False
        info["error"] = str(e)

    except ssl.SSLError as e:
        logger.debug("SSL error for %s: %s", hostname, e)
        info["error"] = str(e)

    except (TimeoutError, socket.gaierror, OSError) as e:
        logger.debug("Connection error for %s: %s", hostname, e)
        info["error"] = str(e)

    return info


def evaluate_tls_protocol(protocol: str) -> dict[str, Any]:
    """
    Evaluate the TLS protocol version.

    Returns a dict with 'secure' bool and 'recommendation' string.
    """
    protocol = protocol.upper() if protocol else ""

    secure_protocols = {"TLSV1.3", "TLSV1.2"}
    deprecated_protocols = {"TLSV1.1", "TLSV1"}
    insecure_protocols = {"SSLV3", "SSLV2"}

    if protocol in secure_protocols:
        return {
            "secure": True,
            "grade": "good",
            "message": f"{protocol} is a secure, modern protocol.",
        }
    elif protocol in deprecated_protocols:
        return {
            "secure": False,
            "grade": "warning",
            "message": f"{protocol} is deprecated and should be upgraded to TLS 1.2+.",
        }
    elif protocol in insecure_protocols:
        return {
            "secure": False,
            "grade": "critical",
            "message": f"{protocol} is insecure and must not be used.",
        }
    else:
        return {
            "secure": False,
            "grade": "unknown",
            "message": f"Unknown protocol: {protocol}",
        }


def evaluate_cipher_suite(cipher: str) -> dict[str, Any]:
    """Evaluate the strength of a cipher suite."""
    cipher_upper = cipher.upper() if cipher else ""

    weak_ciphers = {"RC4", "DES", "3DES", "MD5", "NULL", "EXPORT"}
    strong_indicators = {"AES", "CHACHA20", "GCM", "SHA256", "SHA384"}

    is_weak = any(w in cipher_upper for w in weak_ciphers)
    is_strong = any(s in cipher_upper for s in strong_indicators)

    if is_weak:
        return {
            "secure": False,
            "grade": "critical",
            "message": f"Cipher {cipher} uses weak algorithms.",
        }
    elif is_strong:
        return {
            "secure": True,
            "grade": "good",
            "message": f"Cipher {cipher} uses strong algorithms.",
        }
    else:
        return {
            "secure": True,
            "grade": "acceptable",
            "message": f"Cipher {cipher} is acceptable.",
        }


def _parse_cert_field(field_tuple: tuple) -> dict[str, str]:  # type: ignore
    """Parse a certificate subject/issuer tuple into a flat dict."""
    result: dict[str, str] = {}
    for entry in field_tuple:
        if isinstance(entry, tuple):
            for key, value in entry:
                result[key] = value
    return result


def _parse_cert_date(date_str: str) -> datetime | None:
    """Parse certificate date strings."""
    formats = [
        "%b %d %H:%M:%S %Y %Z",
        "%b  %d %H:%M:%S %Y %Z",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
