"""AI wizard service — three-stage LLM pipeline that drafts an Issue from a
free-form bug description. Used by the SSE endpoint POST /api/issues/ai-draft/.
"""
import json
import logging
from dataclasses import dataclass

from apps.ai.client import LLMClient
from apps.ai.models import LLMConfig, Prompt


logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 20


@dataclass
class AiWizardError(Exception):
    step: int
    code: str
    message: str

    def __str__(self):
        return f"[step {self.step}] {self.code}: {self.message}"


class AiWizardService:
    """Three-stage LLM pipeline for the issue creation wizard.

    Each stage:
      1. classify(description) → {category, scope}
      2. extract(description, classify, modules) → {title, priority, module}
      3. generate(description, classify, extract, labels) → {repro_steps, expected_behavior, labels}

    On any LLM failure or malformed JSON, raises AiWizardError carrying the
    failed step number and a typed error code for the SSE layer to relay.
    """

    def _run_prompt(self, step: int, slug: str, **format_kwargs) -> dict:
        prompt = Prompt.objects.filter(slug=slug, is_active=True).first()
        if prompt is None:
            raise AiWizardError(step=step, code="missing_prompt", message=f"未配置 Prompt: {slug}")

        config = prompt.llm_config or LLMConfig.objects.filter(is_default=True, is_active=True).first()
        if config is None:
            raise AiWizardError(step=step, code="missing_llm_config", message="未配置可用的 LLM")

        try:
            user_prompt = prompt.user_prompt_template.format(**format_kwargs)
        except KeyError as e:
            raise AiWizardError(step=step, code="prompt_format_error", message=f"模板缺失变量 {e}")

        try:
            raw = LLMClient(config).complete(
                model=prompt.llm_model,
                system_prompt=prompt.system_prompt,
                user_prompt=user_prompt,
                temperature=prompt.temperature,
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except Exception as e:
            logger.warning("wizard step=%s LLM call failed: %s", step, e, exc_info=True)
            raise AiWizardError(step=step, code="llm_call_failed", message="AI 调用失败，请重试")

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("wizard step=%s bad JSON: %r", step, raw)
            raise AiWizardError(step=step, code="llm_bad_json", message="AI 返回格式异常，请重试")

    def classify(self, description: str) -> dict:
        return self._run_prompt(step=1, slug="wizard_classify", description=description)
