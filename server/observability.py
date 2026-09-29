"""Privacy-bounded request logging and read-only health checks."""
import json
import re


SERVICE = "gemini-dino-jump"
UNKNOWN = "unknown"

_STATIC_ROUTES = {
    "/api/shared/game_constants.json", "/api/health", "/api/config",
    "/api/webhooks/kakao-share", "/api/observations", "/api/participants/anonymous",
    "/api/me", "/api/me/profile", "/api/referrals/me", "/api/referrals/qualify",
    "/api/referrals/share-reward", "/api/referrals/share-intents",
    "/api/referrals/cooldown-notice/ack", "/api/game-sessions", "/api/leaderboard",
    "/api/ranking/profile", "/api/draws/me", "/api/draws", "/api/claims",
    "/api/events/batch", "/api/admin/session", "/api/admin/overview", "/api/admin/claims",
    "/api/admin/analytics/events", "/api/admin/game-faults",
    "/api/admin/ranking-snapshots", "/api/admin/ranking-contacts", "/api/admin/campaign",
}
_DYNAMIC_ROUTES = (
    (re.compile(r"^/api/game-sessions/[^/]+/(start|checkpoint|finish|fault|abandon)$"), lambda match: f"/api/game-sessions/{{id}}/{match.group(1)}"),
    (re.compile(r"^/api/game-sessions/[^/]+$"), lambda _match: "/api/game-sessions/{id}"),
    (re.compile(r"^/api/referrals/share-intents/[^/]+$"), lambda _match: "/api/referrals/share-intents/{id}"),
    (re.compile(r"^/api/draws/[^/]+/scratch-complete$"), lambda _match: "/api/draws/{id}/scratch-complete"),
    (re.compile(r"^/api/claims/[^/]+/(draft|submit)$"), lambda match: f"/api/claims/{{id}}/{match.group(1)}"),
    (re.compile(r"^/api/admin/claims/[^/]+$"), lambda _match: "/api/admin/claims/{id}"),
    (re.compile(r"^/api/admin/game-faults/[^/]+$"), lambda _match: "/api/admin/game-faults/{id}"),
    (re.compile(r"^/api/admin/ranking-snapshots/[^/]+/(reviews|finalize)$"), lambda match: f"/api/admin/ranking-snapshots/{{id}}/{match.group(1)}"),
    (re.compile(r"^/api/admin/participants/[^/]+$"), lambda _match: "/api/admin/participants/{id}"),
)
_NORMALIZED_ROUTES = _STATIC_ROUTES | {
    "/api/game-sessions/{id}", "/api/game-sessions/{id}/start",
    "/api/game-sessions/{id}/checkpoint", "/api/game-sessions/{id}/finish",
    "/api/game-sessions/{id}/fault", "/api/game-sessions/{id}/abandon",
    "/api/referrals/share-intents/{id}", "/api/draws/{id}/scratch-complete",
    "/api/claims/{id}/draft", "/api/claims/{id}/submit", "/api/admin/claims/{id}",
    "/api/admin/game-faults/{id}", "/api/admin/ranking-snapshots/{id}/reviews",
    "/api/admin/ranking-snapshots/{id}/finalize", "/api/admin/participants/{id}",
    "/api/unknown",
}
_TAG = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_METHODS = {"GET", "HEAD", "POST", "PATCH", "OPTIONS"}
_OPERATION_OUTCOMES = {
    "completed", "failed", "webhook_duplicate", "webhook_expired", "webhook_rejected",
    "webhook_reward_granted", "webhook_reward_blocked", "webhook_no_reward",
    "webhook_not_eligible", "webhook_processing_failed",
}
_AUTH_ERRORS = {"ADMIN_AUTH_REQUIRED", "AUTH_UNAVAILABLE", "WEBHOOK_UNAUTHORIZED"}
_VALIDATION_ERRORS = {"INVALID_BODY", "INVALID_JSON", "INVALID_QUERY", "JSON_REQUIRED", "BODY_TOO_LARGE", "URL_TOO_LONG", "VALIDATION_ERROR", "INVALID_WEBHOOK"}


class HealthCheckFailed(RuntimeError):
    pass


def normalize_route(path):
    if path in _STATIC_ROUTES:
        return path
    for pattern, template in _DYNAMIC_ROUTES:
        match = pattern.fullmatch(path or "")
        if match:
            return template(match)
    return "/api/unknown"


def _tag(value):
    text = str(value or "")
    return text if _TAG.fullmatch(text) else UNKNOWN


def error_class(status, error_code=None, database_failure=None):
    if database_failure == "configuration":
        return "configuration"
    if database_failure:
        return "database"
    if status < 400:
        return "none"
    if error_code in _AUTH_ERRORS:
        return "authentication"
    if error_code == "RATE_LIMITED":
        return "rate_limit"
    if error_code in _VALIDATION_ERRORS:
        return "validation"
    if status >= 500:
        return "internal"
    return "domain"


def request_outcome(status):
    if status >= 500:
        return "server_error"
    if status >= 400:
        return "client_error"
    return "success"


def operation_outcome(route, status, response=None):
    if status >= 400:
        return "failed"
    if route != "/api/webhooks/kakao-share" or not isinstance(response, dict):
        return "completed"
    if response.get("duplicate") is True:
        return "webhook_duplicate"
    if response.get("accepted") is not True:
        return "webhook_processing_failed"
    intent_status = str(response.get("status") or "").lower()
    reward_status = str(response.get("reward_status") or "").lower()
    if intent_status == "expired":
        return "webhook_expired"
    if intent_status == "rejected":
        return "webhook_rejected"
    if intent_status != "confirmed":
        return "webhook_processing_failed"
    if reward_status == "granted":
        return "webhook_reward_granted"
    if reward_status.startswith("blocked_"):
        return "webhook_reward_blocked"
    if reward_status == "no_reward":
        return "webhook_no_reward"
    if reward_status == "not_eligible":
        return "webhook_not_eligible"
    return "webhook_processing_failed"


def request_log(*, environment, campaign, deployment, route, method, status, duration_ms,
                request_id, error_code=None, database_failure=None, operation=None):
    status = int(status) if isinstance(status, int) and 100 <= status <= 599 else 500
    duration = max(0, int(round(duration_ms))) if isinstance(duration_ms, (int, float)) else 0
    return {
        "event": "api_request",
        "service": SERVICE,
        "env": _tag(environment),
        "campaign": _tag(campaign),
        "deployment": _tag(deployment),
        "route": route if route in _NORMALIZED_ROUTES else "/api/unknown",
        "method": method if method in _METHODS else UNKNOWN,
        "status": status,
        "duration_ms": duration,
        "request_id": _tag(request_id),
        "outcome": request_outcome(status),
        "operation_outcome": operation if operation in _OPERATION_OUTCOMES else ("failed" if status >= 400 else "completed"),
        "error_class": error_class(status, error_code, database_failure),
        "error_code": _tag(error_code) if error_code else None,
        "database_failure": _tag(database_failure) if database_failure else None,
    }


def serialize(record):
    return json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"


def health_snapshot(conn, settings, guard, schema):
    row = conn.execute(f"""select 1::int database_check,c.status campaign_status,c.game_version,
      (select count(*)::int from {schema}.inventory_item where status='AVAILABLE') inventory_remaining
      from (select 1) heartbeat left join {schema}.campaign c on c.id=%s""", (guard["campaign_id"],)).fetchone()
    if not row or row.get("database_check") != 1 or not row.get("campaign_status"):
        raise HealthCheckFailed("DATABASE_HEALTH_CHECK_FAILED")
    remaining = row["inventory_remaining"]
    return {
        "ok": True,
        "service": SERVICE,
        "environment": settings.environment,
        "deployment": settings.deployment,
        "database": "ready",
        "schema_valid": True,
        "project_ref": settings.project_ref,
        "schema": settings.schema_name,
        "synthetic_only": False,
        "gameplay_synthetic_only": settings.synthetic_only,
        "top3_contact_collection_enabled": True,
        "test_seed": guard["test_seed"],
        "inventory_remaining": remaining,
        "test_inventory_remaining": remaining if settings.synthetic_only else None,
        "campaign_status": row["campaign_status"],
    }
