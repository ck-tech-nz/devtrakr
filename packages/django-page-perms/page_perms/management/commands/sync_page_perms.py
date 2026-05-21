from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from page_perms.conf import get_config
from page_perms.models import PageRoute


class Command(BaseCommand):
    help = (
        "Sync page routes and group permissions from the page_perms JSON seed file "
        "(PAGE_PERMS_SEED_FILE) into the database."
    )

    def handle(self, *args, **options):
        config = get_config()
        self._sync_routes(config.get("SEED_ROUTES", []))
        self._sync_groups(config.get("SEED_GROUPS", {}))

    def _resolve_permission(self, perm_string):
        """Resolve 'app_label.codename' or just 'codename' to Permission."""
        if not perm_string:
            return None
        if "." in perm_string:
            app_label, codename = perm_string.split(".", 1)
            try:
                return Permission.objects.get(
                    content_type__app_label=app_label, codename=codename
                )
            except Permission.DoesNotExist:
                self.stderr.write(f"  Warning: permission '{perm_string}' not found, skipping")
                return None
        perms = Permission.objects.filter(codename=perm_string)
        if perms.count() == 1:
            return perms.first()
        if perms.count() > 1:
            self.stderr.write(f"  Warning: ambiguous codename '{perm_string}', skipping")
        else:
            self.stderr.write(f"  Warning: permission '{perm_string}' not found, skipping")
        return None

    def _sync_routes(self, seed_routes):
        self.stdout.write("Syncing page routes...")
        for route_data in seed_routes:
            path = route_data["path"]
            perm_string = route_data.get("permission")
            permission = self._resolve_permission(perm_string) if perm_string else None

            defaults = {
                "label": route_data["label"],
                "icon": route_data.get("icon", ""),
                "permission": permission,
                "show_in_nav": route_data.get("show_in_nav", True),
                "sort_order": route_data.get("sort_order", 0),
                "is_active": route_data.get("is_active", True),
                "meta": route_data.get("meta", {}),
                # Respect explicit source in JSON so dump→sync round-trip preserves
                # whether a route was originally created via UI (manual) or seed.
                "source": route_data.get("source", "seed"),
            }

            route, created = PageRoute.objects.update_or_create(
                path=path, defaults=defaults
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"  {action}: {path}")

        self.stdout.write(self.style.SUCCESS(f"  Synced {len(seed_routes)} routes"))

    def _sync_groups(self, seed_groups):
        self.stdout.write("Syncing groups...")

        # First pass: resolve all group permission sets (needed for inherit)
        resolved = {}
        for group_name, config in seed_groups.items():
            perms = set()

            if "apps" in config:
                perms.update(
                    Permission.objects.filter(
                        content_type__app_label__in=config["apps"]
                    )
                )

            if "permissions" in config:
                for entry in config["permissions"]:
                    if "." in entry:
                        # app_label.codename — unambiguous (used by dump_page_perms)
                        perm = self._resolve_permission(entry)
                        if perm:
                            perms.add(perm)
                    else:
                        # Bare codename — match every Permission with this codename
                        perms.update(Permission.objects.filter(codename=entry))

            if "permissions_startswith" in config:
                for prefix in config["permissions_startswith"]:
                    perms.update(
                        Permission.objects.filter(codename__startswith=prefix)
                    )

            if "exclude_permissions" in config:
                for codename in config["exclude_permissions"]:
                    perms -= set(Permission.objects.filter(codename=codename))

            resolved[group_name] = perms

        # Second pass: handle inherit (snapshot semantics)
        for group_name, config in seed_groups.items():
            if "inherit" in config:
                parent_name = config["inherit"]
                if parent_name in resolved:
                    resolved[group_name].update(resolved[parent_name])
                else:
                    self.stderr.write(
                        f"  Warning: inherit target '{parent_name}' not found for group '{group_name}'"
                    )

        # Third pass: create/update groups
        for group_name, perms in resolved.items():
            group, created = Group.objects.get_or_create(name=group_name)
            group.permissions.set(perms)
            action = "Created" if created else "Updated"
            self.stdout.write(f"  {action} group: {group_name} ({len(perms)} permissions)")

        self.stdout.write(self.style.SUCCESS(f"  Synced {len(seed_groups)} groups"))
