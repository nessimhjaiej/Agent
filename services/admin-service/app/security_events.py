from __future__ import annotations

import json
from urllib import error, request

from app.config import Settings


def emit_security_event(
    settings: Settings,
    *,
    event_type: str,
    severity: str,
    title: str,
    message: str,
    metadata: dict | None = None,
) -> None:
    if not settings.security_base_url:
        return

    payload = json.dumps(
        {
            "event_type": event_type,
            "source_service": settings.app_name,
            "severity": severity,
            "title": title,
            "message": message,
            "metadata": metadata or {},
        }
    ).encode("utf-8")
    endpoint = f"{settings.security_base_url.rstrip('/')}/security/events"
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=0.4):
            pass
    except (error.URLError, TimeoutError, ValueError):
        pass

