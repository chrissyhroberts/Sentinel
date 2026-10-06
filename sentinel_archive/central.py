from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any


class CentralError(RuntimeError):
    pass


@dataclass(frozen=True)
class CentralConfig:
    base_url: str
    project_id: str
    audit_form_id: str = "sentinel_project_audit"
    audit_form_version: str = "1"
    token_env: str = "ODK_CENTRAL_TOKEN"
    timestamp_policy: str = "preferred"
    timestamp_url: str = "https://tsr.open-tsa.eu"
    server_audit_start: str = ""
    server_audit_enabled: bool = False
    validation_form_ids: tuple[str, ...] = ()


class CentralClient:
    """Small read/read-submit ODK Central client with no local data cache."""

    def __init__(self, config: CentralConfig, token: str | None = None, *, debug: bool = False):
        self.config = config
        self.token = token or os.environ.get(config.token_env)
        self.base_url = config.base_url.rstrip("/")
        self.debug = debug
        self._user_cache: dict[str, dict[str, Any] | None] = {}

    @classmethod
    def login(cls, config: CentralConfig, email: str, password: str, *, debug: bool = False) -> "CentralClient":
        client = cls(config, token="session-login", debug=debug)
        response = client._request(
            "POST", "/v1/sessions", accept="application/json",
            json_body={"email": email, "password": password},
        )
        token = response.get("token") if isinstance(response, dict) else None
        if not token:
            raise CentralError("Central login did not return a session token")
        return cls(config, token=str(token), debug=debug)

    def get_json(self, path: str) -> Any:
        return self._request("GET", path, accept="application/json")

    def get_bytes(self, path: str) -> bytes:
        result = self._request("GET", path, accept="application/octet-stream", raw=True)
        assert isinstance(result, bytes)
        return result

    def submit(self, form_id: str, xml: bytes, attachments: dict[str, bytes]) -> None:
        fields = {"xml_submission_file": ("submission.xml", xml, "text/xml")}
        self._request(
            "POST",
            f"/v1/projects/{_quote(self.config.project_id)}/submission",
            accept="text/xml",
            raw=True,
            multipart=fields,
            extra_headers={"X-OpenRosa-Version": "1.0"},
        )
        if attachments:
            root = ET.fromstring(xml)
            instance = next((node.text for node in root.iter() if node.tag.endswith("instanceID")), None)
            if not instance:
                raise CentralError("Audit submission XML did not contain an instanceID")
            for filename, data in attachments.items():
                # Central's attachment endpoint receives opaque binary data.
                # In particular, application/json can be parsed as an API body
                # instead of being stored as the JSON attachment bytes.
                self.upload_attachment(form_id, instance, filename, data,
                                       content_type="application/octet-stream")

    def upload_attachment(self, form_id: str, instance_id: str, filename: str, data: bytes,
                          content_type: str | None = None) -> None:
        path = self._submission_path(form_id, instance_id) + f"/attachments/{_quote(filename)}"
        self._request("POST", path, accept="application/json", raw_body=data,
                      content_type=content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream")

    def forms(self, *, deleted: bool = False) -> list[dict[str, Any]]:
        suffix = "?deleted=true" if deleted else ""
        return _items(self.get_json(f"/v1/projects/{_quote(self.config.project_id)}/forms{suffix}"))

    def project(self) -> dict[str, Any]:
        value = self._request(
            "GET", f"/v1/projects/{_quote(self.config.project_id)}?forms=true",
            accept="application/json", extra_headers={"X-Extended-Metadata": "true"},
        )
        return dict(value)

    def server_audits(self, *, start: str | None = None, limit: int = 1000,
                      offset: int = 0) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        while True:
            query = f"limit={int(limit)}&offset={int(offset)}"
            if start:
                query += f"&start={urllib.parse.quote(str(start), safe='') }"
            path = f"/v1/audits?{query}"
            value = self._request(
                "GET", path, accept="application/json",
                extra_headers={"X-Extended-Metadata": "true"},
            )
            page = _items(value)
            result.extend(page)
            if len(page) < limit:
                return result
            offset += limit

    def submissions(self, form_id: str) -> list[dict[str, Any]]:
        return _items(self.get_json(self._form_path(form_id) + "/submissions"))

    def form_versions(self, form_id: str) -> list[dict[str, Any]]:
        return _items(self.get_json(self._form_path(form_id) + "/versions"))

    def form_version_bytes(self, form_id: str, version: str, extension: str) -> bytes:
        path = self._form_path(form_id) + f"/versions/{_quote(version)}.{extension}"
        return self.get_bytes(path)

    def versions(self, form_id: str, instance_id: str) -> list[dict[str, Any]]:
        path = self._submission_path(form_id, instance_id) + "/versions"
        return _items(self.get_json(path))

    def submission(self, form_id: str, instance_id: str) -> dict[str, Any]:
        return dict(self.get_json(self._submission_path(form_id, instance_id)))

    def user(self, actor_id: Any) -> dict[str, Any] | None:
        """Return a Central Web User, cached for the duration of this run.

        App Users and public-link actors are not Web Users and therefore may
        not have an email address in the Users API.  Callers should treat a
        missing result as an expected fallback case.
        """
        key = str(actor_id or "")
        if not key:
            return None
        if key in self._user_cache:
            return self._user_cache[key]
        try:
            result = dict(self.get_json(f"/v1/users/{_quote(key)}"))
        except CentralError as error:
            if "returned HTTP 404" not in str(error):
                raise
            result = None
        self._user_cache[key] = result
        return result

    def actor_email(self, actor_id: Any) -> str:
        user = self.user(actor_id)
        if not user:
            return ""
        value = user.get("email") or user.get("emailAddress")
        return str(value or "")

    def version_metadata(self, form_id: str, instance_id: str, version_id: str) -> dict[str, Any]:
        return dict(self.get_json(self._submission_path(form_id, instance_id) + f"/versions/{_quote(version_id)}"))

    def version_xml(self, form_id: str, instance_id: str, version_id: str) -> bytes:
        path = self._submission_path(form_id, instance_id) + f"/versions/{_quote(version_id)}.xml"
        return self.get_bytes(path)

    def submission_xml(self, form_id: str, instance_id: str) -> bytes:
        result = self._request(
            "GET", self._submission_path(form_id, instance_id) + ".xml",
            accept="application/xml", raw=True,
        )
        assert isinstance(result, bytes)
        return result

    def attachment_bytes(self, form_id: str, instance_id: str, version_id: str, filename: str) -> bytes:
        path = (self._submission_path(form_id, instance_id)
                + f"/versions/{_quote(version_id)}/attachments/{_quote(filename)}")
        return self.get_bytes(path)

    def version_attachments(self, form_id: str, instance_id: str, version_id: str) -> list[dict[str, Any]]:
        path = (self._submission_path(form_id, instance_id)
                + f"/versions/{_quote(version_id)}/attachments")
        return _items(self.get_json(path))

    def audits(self, form_id: str, instance_id: str) -> list[dict[str, Any]]:
        value = self._request(
            "GET", self._submission_path(form_id, instance_id) + "/audits",
            accept="application/json", extra_headers={"X-Extended-Metadata": "true"},
        )
        return _items(value)

    def comments(self, form_id: str, instance_id: str) -> list[dict[str, Any]]:
        return _items(self.get_json(self._submission_path(form_id, instance_id) + "/comments"))

    def diffs(self, form_id: str, instance_id: str) -> Any:
        return self.get_json(self._submission_path(form_id, instance_id) + "/diffs")

    def _form_path(self, form_id: str) -> str:
        return f"/v1/projects/{_quote(self.config.project_id)}/forms/{_quote(form_id)}"

    def _submission_path(self, form_id: str, instance_id: str) -> str:
        return self._form_path(form_id) + f"/submissions/{_quote(instance_id)}"

    def _request(self, method: str, path: str, *, accept: str, raw: bool = False,
                 multipart: dict[str, tuple[str, bytes, str]] | None = None,
                 json_body: dict[str, Any] | None = None,
                 raw_body: bytes | None = None,
                 content_type: str | None = None,
                 extra_headers: dict[str, str] | None = None) -> Any:
        body = None
        headers = {"Accept": accept}
        if extra_headers:
            headers.update(extra_headers)
        if self.token and self.token != "session-login":
            headers["Authorization"] = f"Bearer {self.token}"
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if raw_body is not None:
            body = raw_body
            headers["Content-Type"] = content_type or "application/octet-stream"
        if multipart is not None:
            boundary = "----SentinelBoundary7d3c4f"
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            body = _multipart(boundary, multipart)
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            request = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    data = response.read()
                break
            except urllib.error.HTTPError as error:
                detail = error.read(2048).decode("utf-8", "replace")
                raise CentralError(f"Central {method} {path} returned HTTP {error.code}: {detail}") from error
            except (urllib.error.URLError, ConnectionError, BrokenPipeError) as error:
                if attempt + 1 >= attempts:
                    reason = getattr(error, "reason", None) or str(error)
                    raise CentralError(f"Central {method} {path} failed after {attempts} attempts: {reason}") from error
                if self.debug:
                    print(f"[debug] Central {method} {path} connection failed; retrying ({attempt + 2}/{attempts})", file=sys.stderr)
                time.sleep(1.5 * (attempt + 1))
        if raw:
            return data
        if not data:
            return {}
        try:
            return json.loads(data)
        except json.JSONDecodeError as error:
            raise CentralError(f"Central returned non-JSON data for {path}") from error


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value]
    if isinstance(value, dict):
        for key in ("items", "forms", "submissions", "versions", "audits", "comments"):
            if isinstance(value.get(key), list):
                return [dict(item) for item in value[key]]
    raise CentralError("Unexpected Central collection response")


def _multipart(boundary: str, fields: dict[str, tuple[str, bytes, str]]) -> bytes:
    chunks: list[bytes] = []
    for name, (filename, content, content_type) in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            content,
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks)
