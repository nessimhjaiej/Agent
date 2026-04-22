from __future__ import annotations

import json
from urllib import error, request


def emit_security_event(
    security_base_url: str,
    *,
    source_service: str,
    event_type: str,
    severity: str,
    title: str,
    message: str,
    metadata: dict | None = None,
) -> None:
    if not security_base_url:
        return

    payload = json.dumps(
        {
            "event_type": event_type,
            "source_service": source_service,
            "severity": severity,
            "title": title,
            "message": message,
            "metadata": metadata or {},
        }
    ).encode("utf-8")
    endpoint = f"{security_base_url.rstrip('/')}/security/events"
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

