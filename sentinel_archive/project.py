from __future__ import annotations

import hashlib


AUDIT_FORM_ID = "sentinel_project_audit"


def audit_instance_id(project_id: str, form_id: str, instance_id: str, version_id: str) -> str:
    """Return a deterministic Central instance ID for an audit record."""
    material = "\x1f".join((project_id, form_id, instance_id, version_id)).encode()
    return "uuid:sentinel-" + hashlib.sha256(material).hexdigest()


def checkpoint_instance_id(project_id: str) -> str:
    material = ("checkpoint\x1f" + project_id).encode()
    return "uuid:sentinel-checkpoint-" + hashlib.sha256(material).hexdigest()
