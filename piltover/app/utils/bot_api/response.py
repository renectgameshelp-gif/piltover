from __future__ import annotations

import json
from typing import Any


def api_ok(result: Any) -> dict[str, Any]:
    return {"ok": True, "result": result}


def api_error(description: str, error_code: int = 400, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"ok": False, "description": description, "error_code": error_code}
    if parameters is not None:
        body["parameters"] = parameters
    return body


def http_response(body: dict[str, Any]) -> bytes:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = [
        "HTTP/1.1 200 OK",
        f"Content-Length: {len(payload)}",
        "Content-Type: application/json; charset=utf-8",
        "Connection: close",
        "",
        "",
    ]
    return "\r\n".join(headers).encode("ascii") + payload