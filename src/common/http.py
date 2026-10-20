"""Helpers for building API Gateway proxy responses."""
import json
import os

_ALLOWED_ORIGIN = os.environ.get("CORS_ALLOW_ORIGIN", "*")


def _cors_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": _ALLOWED_ORIGIN,
        "Access-Control-Allow-Headers": "Content-Type, x-api-key",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
    }


def response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": _cors_headers(),
        "body": json.dumps(body, default=str),
    }


def ok(body: dict, status_code: int = 202) -> dict:
    return response(status_code, body)


def error(status_code: int, code: str, message: str, **extra) -> dict:
    body = {"error": code, "message": message}
    body.update(extra)
    return response(status_code, body)
