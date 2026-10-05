from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class CentralError(RuntimeError):
    pass


@dataclass(frozen=True)
class CentralConfig:
    base_url: str
    project_id: str
    audit_form_id: str = "sentinel_project_audit"
    token_env: str = "ODK_CENTRAL_TOKEN"


class CentralClient:
    """Small read/read-submit ODK Central client with no local data cache."""

    def __init__(self, config: CentralConfig, token: str | None = None):
        self.config = config
        self.token = token or os.environ.get(config.token_env)
        self.base_url = config.base_url.rstrip("/")

    @classmethod
    def login(cls, config: CentralConfig, email: str, password: str) -> "CentralClient":
        client = cls(config, token="session-login")
        response = client._request(
            "POST", "/v1/sessions", accept="application/json",
            json_body={"email": email, "password": password},
        )
        token = response.get("token") if isinstance(response, dict) else None
        if not token:
            raise CentralError("Central login did not return a session token")
        return cls(config, token=str(token))

    def get_json(self, path: str) -> Any:
        return self._request("GET", path, accept="application/json")

    def get_bytes(self, path: str) -> bytes:
        result = self._request("GET", path, accept="application/octet-stream", raw=True)
        assert isinstance(result, bytes)
        return result

    def submit(self, form_id: str, xml: bytes, attachments: dict[str, bytes]) -> None:
        fields = {"xml_submission_file": ("submission.xml", xml, "text/xml")}
        fields.update({name: (name, data, "application/octet-stream") for name, data in attachments.items()})
        self._request(
            "POST",
            f"/v1/projects/{_quote(self.config.project_id)}/forms/{_quote(form_id)}/submissions",
            accept="application/json",
            multipart=fields,
        )

    def forms(self) -> list[dict[str, Any]]:
        return _items(self.get_json(f"/v1/projects/{_quote(self.config.project_id)}/forms"))

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

    def version_metadata(self, form_id: str, instance_id: str, version_id: str) -> dict[str, Any]:
        return dict(self.get_json(self._submission_path(form_id, instance_id) + f"/versions/{_quote(version_id)}"))

    def version_xml(self, form_id: str, instance_id: str, version_id: str) -> bytes:
        path = self._submission_path(form_id, instance_id) + f"/versions/{_quote(version_id)}.xml"
        return self.get_bytes(path)

    def attachment_bytes(self, form_id: str, instance_id: str, version_id: str, filename: str) -> bytes:
        path = (self._submission_path(form_id, instance_id)
                + f"/versions/{_quote(version_id)}/attachments/{_quote(filename)}")
        return self.get_bytes(path)

    def audits(self, form_id: str, instance_id: str) -> list[dict[str, Any]]:
        return _items(self.get_json(self._submission_path(form_id, instance_id) + "/audits"))

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
                 json_body: dict[str, Any] | None = None) -> Any:
        body = None
        headers = {"Accept": accept}
        if self.token and self.token != "session-login":
            headers["Authorization"] = f"Bearer {self.token}"
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if multipart is not None:
            boundary = "----SentinelBoundary7d3c4f"
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            body = _multipart(boundary, multipart)
        request = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read(2048).decode("utf-8", "replace")
            raise CentralError(f"Central {method} {path} returned HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise CentralError(f"Central {method} {path} failed: {error.reason}") from error
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
