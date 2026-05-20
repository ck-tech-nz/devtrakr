"""Sync AI Prompt rows from seed_prompts/*.json (file = source of truth).

Workflow:
  - Default (no flags): insert any slug whose JSON file exists but the DB
    row does not. Safe to run on every deploy.
  - --force <slug>: overwrite content fields for that slug from its JSON
    file. llm_model / llm_config are preserved so per-env LLM binding
    survives admin tuning.
  - --force-all: same as --force for every seed file.

Required JSON fields: name, system_prompt, user_prompt_template, temperature.
Slug is inferred from the filename stem (e.g. `wizard_classify.json` →
`wizard_classify`); if the JSON also includes a `slug` field, it must match.
Optional: llm_model (used only on insert; ignored on --force), is_active
(default true).
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.ai.models import LLMConfig, Prompt


SEED_DIR = Path(__file__).resolve().parents[2] / "seed_prompts"

CONTENT_FIELDS = ("name", "system_prompt", "user_prompt_template", "temperature")


def _load_seed_files():
    for path in sorted(SEED_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = [k for k in CONTENT_FIELDS if k not in data]
        if missing:
            raise CommandError(f"{path.name}: missing required fields {missing}")
        slug_from_file = data.get("slug")
        slug = slug_from_file or path.stem
        if slug_from_file and slug_from_file != path.stem:
            raise CommandError(
                f"{path.name}: slug '{slug_from_file}' does not match filename stem '{path.stem}'"
            )
        yield path.name, slug, data


def _default_llm_config():
    return (
        LLMConfig.objects.filter(is_default=True, is_active=True).first()
        or LLMConfig.objects.filter(is_active=True).order_by("id").first()
    )


def _inherit_llm_model():
    template = (
        Prompt.objects.filter(slug="wizard_extract", is_active=True).first()
        or Prompt.objects.filter(is_active=True).exclude(llm_model="").order_by("id").first()
    )
    return template.llm_model if template else ""


class Command(BaseCommand):
    help = "Sync AI Prompt rows from apps/ai/seed_prompts/*.json"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--force", metavar="SLUG",
                           help="overwrite content for one slug from its seed file")
        group.add_argument("--force-all", action="store_true",
                           help="overwrite content for every seed file")

    @transaction.atomic
    def handle(self, *args, force=None, force_all=False, **opts):
        seen_slugs = set()
        for fname, slug, data in _load_seed_files():
            seen_slugs.add(slug)
            existing = Prompt.objects.filter(slug=slug).first()

            content = {k: data[k] for k in CONTENT_FIELDS}
            content["is_active"] = data.get("is_active", True)

            if existing is None:
                llm_config = _default_llm_config()
                if llm_config is None:
                    self.stdout.write(self.style.WARNING(
                        f"skip {slug} ({fname}): no active LLMConfig to bind to"))
                    continue
                llm_model = data.get("llm_model") or _inherit_llm_model()
                Prompt.objects.create(
                    slug=slug, llm_config=llm_config, llm_model=llm_model, **content,
                )
                self.stdout.write(self.style.SUCCESS(f"created {slug}"))
                continue

            if force_all or force == slug:
                for k, v in content.items():
                    setattr(existing, k, v)
                existing.save()
                self.stdout.write(self.style.SUCCESS(f"updated {slug}"))
            else:
                self.stdout.write(f"skip {slug} (exists; pass --force {slug} to overwrite)")

        if force and force not in seen_slugs:
            raise CommandError(f"--force {force}: no seed file found for that slug")
