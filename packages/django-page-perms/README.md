# django-page-perms

Dynamic page-permission mapping for Django + DRF projects. Maps frontend routes to Django permissions via a database-backed configuration, with API endpoints for runtime management.

## Installation

```bash
pip install django-page-perms
# or with uv:
uv add django-page-perms
```

## Quick Start

1. Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "page_perms",
]
```

2. Include URLs:

```python
# urls.py
path("api/page-perms/", include("page_perms.urls")),
```

3. Run migrations:

```bash
python manage.py migrate page_perms
```

4. Configure seed data in `settings.py` (see Configuration below).

5. Sync:

```bash
python manage.py sync_page_perms
```

## Configuration

```python
PAGE_PERMS = {
    # Permission class for GET /routes/ (default: all authenticated users)
    "ROUTE_LIST_PERMISSION": "IsAuthenticated",

    # Routes that cannot be deleted or deactivated via API
    "PROTECTED_PATHS": ["/app/permissions"],

    # Seed route data (synced by sync_page_perms command)
    "SEED_ROUTES": [
        # A group row — renders as a parent in the sidebar; not a navigable page.
        # By convention, use a synthetic path prefixed with `#group:`.
        {
            "path": "#group:dashboards",
            "label": "Dashboards",
            "icon": "folder-icon",
            "is_group": True,
            "sort_order": 0,
        },
        # A leaf route, linked to its parent group by `parent` (the parent's path).
        {
            "path": "/app/dashboard",
            "label": "Dashboard",
            "icon": "dashboard-icon",
            "permission": "myapp.view_dashboard",  # app_label.codename format, or None
            "parent": "#group:dashboards",  # null/omit for top-level
            "sort_order": 1,
            "meta": {},  # arbitrary JSON for frontend use
        },
    ],

    # Seed group-permission assignments
    "SEED_GROUPS": {
        "Admin": {"apps": ["myapp"]},                        # all perms for listed apps
        "Developer": {"permissions": ["view_item"]},          # explicit codenames
        "Manager": {"inherit": "Developer", "permissions": ["add_item"]},  # snapshot inherit
        "Viewer": {"permissions_startswith": ["view_"]},      # prefix match
    },
}
```

### SEED_GROUPS options

| Key | Description |
|-----|-------------|
| `apps` | Grant all permissions for listed Django app labels |
| `permissions` | Grant permissions by exact codename (matched across all apps) |
| `permissions_startswith` | Grant permissions where codename starts with prefix |
| `inherit` | Merge another group's seed permissions (snapshot at sync time, not live) |

All options can be combined; the final permission set is the union.

## API Endpoints

### Routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/routes/` | Authenticated | List active routes. Superuser: add `?all=true` for inactive |
| POST | `/routes/` | Superuser | Create route |
| PATCH | `/routes/{id}/` | Superuser | Partial update (any subset of fields) |
| DELETE | `/routes/{id}/` | Superuser | Delete route (protected paths blocked) |

**Response format:**

```json
{
  "id": 1,
  "path": "/app/dashboard",
  "label": "Dashboard",
  "icon": "icon-class",
  "permission": "myapp.view_dashboard",
  "parent": "#group:dashboards",
  "is_group": false,
  "show_in_nav": true,
  "sort_order": 1,
  "is_active": true,
  "meta": {},
  "source": "seed"
}
```

The `permission` field accepts and returns `"app_label.codename"` strings. Set to `null` for no permission requirement.

The `parent` field is the parent route's `path` (a string), or `null` for top-level entries. The `is_group` flag marks rows that are sidebar groups rather than navigable pages — they have children and no `permission` of their own. Only one level of nesting is supported (a group cannot have a group parent); this is enforced by `PageRoute.clean()`.

### Permissions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/permissions/` | Superuser | List all permissions with source (model/custom) |
| POST | `/permissions/` | Superuser | Create custom permission (`codename` + `name`) |
| DELETE | `/permissions/{id}/` | Superuser | Delete custom permission (model perms blocked) |

### Groups

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/groups/` | Superuser | List groups with their permissions |
| PATCH | `/groups/{id}/` | Superuser | Set group permissions (list of `"app_label.codename"` strings) |

## Frontend Integration Guide

### 1. Fetch route config at startup

On login, call `GET /api/page-perms/routes/` to get the full route-permission mapping. Cache the result for the session.

### 2. Build navigation

Filter routes where `show_in_nav` is true and `is_active` is true. For each route, check if the current user has the required `permission` (from your user/auth endpoint). Hide routes the user cannot access.

To render a **two-level hierarchy**, group the rows by `parent`:

1. Pick rows where `is_group: true` — these become group headers.
2. For each group, pick rows where `parent` equals the group's `path` — these are its children.
3. Rows with `parent: null` and `is_group: false` render at the top level.
4. Hide a group entirely if all its children fail your visibility/permission filters.

### 3. Build route guard

From the routes response, build a `path → permission` map. In your router middleware, check if the current route matches any path prefix. If it does and the user lacks the permission, redirect to a forbidden page.

### 4. Handle `meta` field

The `meta` JSON field is for frontend-specific data (e.g., feature flags, service keys). The backend does not interpret it.

### 5. Error handling

If the routes API fails, do not fall back to hardcoded routes. Show an error state instead. This prevents stale permission data from causing security issues.
