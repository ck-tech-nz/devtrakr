import json
import sys
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from page_perms.models import PageRoute


class Command(BaseCommand):
    help = (
        "Dump current PageRoute + Group state to the page_perms JSON seed file. "
        "Preserves non-derived keys (route_list_permission, protected_paths) "
        "from the existing file."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--stdout",
            action="store_true",
            help="Print JSON to stdout instead of writing the seed file.",
        )
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Write to this path instead of PAGE_PERMS_SEED_FILE.",
        )

    def handle(self, *args, **options):
        seed_file = options["output"] or getattr(settings, "PAGE_PERMS_SEED_FILE", None)
        if not options["stdout"] and not seed_file:
            raise CommandError(
                "PAGE_PERMS_SEED_FILE is not configured. "
                "Use --stdout or --output PATH."
            )

        existing = self._read_existing(seed_file) if seed_file else {}

        payload = {
            "route_list_permission": existing.get("route_list_permission", "IsAuthenticated"),
            "protected_paths": existing.get("protected_paths", ["/app/permissions"]),
            "seed_routes": self._dump_routes(),
            "seed_groups": self._dump_groups(),
        }

        rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

        if options["stdout"]:
            sys.stdout.write(rendered)
            return

        target = Path(seed_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"Dumped {len(payload['seed_routes'])} routes and "
                f"{len(payload['seed_groups'])} groups to {target}"
            )
        )

    def _read_existing(self, path):
        p = Path(path)
        if not p.exists():
            return {}
        try:
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise CommandError(f"Existing seed file is not valid JSON: {e}")

    def _dump_routes(self):
        rows = []
        qs = PageRoute.objects.select_related("permission__content_type").order_by(
            "sort_order", "pk"
        )
        for route in qs:
            perm = route.permission
            perm_ref = (
                f"{perm.content_type.app_label}.{perm.codename}" if perm else None
            )
            rows.append({
                "path": route.path,
                "label": route.label,
                "icon": route.icon,
                "permission": perm_ref,
                "sort_order": route.sort_order,
                "show_in_nav": route.show_in_nav,
                "is_active": route.is_active,
                "meta": route.meta or {},
                "source": route.source,
            })
        return rows

    def _dump_groups(self):
        groups = {}
        qs = Group.objects.prefetch_related(
            "permissions__content_type"
        ).order_by("name")
        for group in qs:
            perms = [
                f"{p.content_type.app_label}.{p.codename}"
                for p in group.permissions.all()
            ]
            perms.sort()
            groups[group.name] = {"permissions": perms}
        return groups
