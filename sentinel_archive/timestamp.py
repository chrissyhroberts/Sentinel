from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


class TimestampError(RuntimeError):
    pass


@dataclass(frozen=True)
class TimestampEvidence:
    status: str
    time: str = ""
    token: bytes = b""
    certificate: bytes = b""
    detail: str = ""


def timestamp_manifest(data: bytes, url: str, timeout: int = 60) -> TimestampEvidence:
    """Obtain and minimally validate an RFC3161 response from an OpenTSA URL."""
    digest = hashlib.sha256(data).hexdigest().lower()
    with tempfile.TemporaryDirectory(prefix="sentinel-tsa-") as temporary:
        root = Path(temporary)
        payload = root / "manifest.bin"
        query = root / "request.tsq"
        response = root / "response.tsr"
        token_der = root / "token.der"
        payload.write_bytes(data)
        _openssl(["ts", "-query", "-data", str(payload), "-sha256", "-cert", "-out", str(query)])
        request = urllib.request.Request(
            url,
            data=query.read_bytes(),
            headers={"Content-Type": "application/timestamp-query", "Accept": "application/timestamp-reply"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as connection:
                token = connection.read()
        except (urllib.error.URLError, TimeoutError) as error:
            raise TimestampError(str(error)) from error
        response.write_bytes(token)
        text = _openssl(["ts", "-reply", "-in", str(response), "-text"])
        if not re.search(r"Status:\s+Granted", text, re.IGNORECASE):
            raise TimestampError("TSA did not grant the timestamp request")
        returned_hash = _message_hash(text)
        if returned_hash != digest:
            raise TimestampError("TSA response imprint does not match the manifest")
        certificate = b""
        try:
            _openssl(["ts", "-reply", "-in", str(response), "-token_out", "-out", str(token_der)])
            certificate = _openssl_bytes(["pkcs7", "-inform", "DER", "-in", str(token_der), "-print_certs"])
        except TimestampError:
            # The RFC3161 token remains the authoritative evidence attachment.
            pass
        return TimestampEvidence(
            status="rfc3161_verified",
            time=_timestamp_time(text),
            token=token,
            certificate=certificate,
            detail="OpenTSA RFC3161 response verified against manifest SHA-256",
        )


def _openssl(arguments: list[str]) -> str:
    return _openssl_bytes(arguments).decode("utf-8", "replace")


def _openssl_bytes(arguments: list[str]) -> bytes:
    try:
        result = subprocess.run(["openssl", *arguments], capture_output=True, check=False)
    except OSError as error:
        raise TimestampError(f"OpenSSL is unavailable: {error}") from error
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise TimestampError(detail or "OpenSSL timestamp operation failed")
    return result.stdout


def _message_hash(text: str) -> str:
    section_match = re.search(r"Message data:\s*(.*?)\nSerial number:", text, re.DOTALL)
    if not section_match:
        raise TimestampError("TSA response did not expose a message imprint")
    octets: list[str] = []
    for line in section_match.group(1).splitlines():
        match = re.match(r"\s*[0-9A-Fa-f]{4}\s+-\s+([0-9A-Fa-f\s-]+?)\s{2,}", line)
        if match:
            octets.extend(re.findall(r"[0-9A-Fa-f]{2}", match.group(1)))
    if not octets:
        raise TimestampError("TSA response did not expose a message imprint")
    return "".join(octets).lower()


def _timestamp_time(text: str) -> str:
    match = re.search(r"Time stamp:\s*([^\r\n]+)", text)
    return match.group(1).strip() if match else ""
