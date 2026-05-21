import json
from pathlib import Path

from django.conf import settings


DEFAULTS = {
    "ROUTE_LIST_PERMISSION": "IsAuthenticated",
    "PROTECTED_PATHS": ["/app/permissions"],
    "SEED_ROUTES": [],
    "SEED_GROUPS": {},
}

_JSON_KEY_MAP = {
    "route_list_permission": "ROUTE_LIST_PERMISSION",
    "protected_paths": "PROTECTED_PATHS",
    "seed_routes": "SEED_ROUTES",
    "seed_groups": "SEED_GROUPS",
}


def _load_from_file(path):
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return {_JSON_KEY_MAP[k]: v for k, v in raw.items() if k in _JSON_KEY_MAP}


def get_config():
    # Inline dict override (used in tests) wins over file loading
    user_config = getattr(settings, "PAGE_PERMS", None)
    if user_config is not None:
        return {**DEFAULTS, **user_config}

    seed_file = getattr(settings, "PAGE_PERMS_SEED_FILE", None)
    if seed_file:
        return {**DEFAULTS, **_load_from_file(seed_file)}

    return dict(DEFAULTS)
