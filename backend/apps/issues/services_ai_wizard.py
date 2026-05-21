"""AI wizard service — three-stage LLM pipeline that drafts an Issue from a
free-form bug description. Used by the SSE endpoint POST /api/issues/ai-draft/.
"""
import json
import logging
import re
from dataclasses import dataclass

from apps.ai.client import LLMClient
from apps.ai.models import Prompt


logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 20


@dataclass
class AiWizardError(Exception):
    step: int
    code: str
    message: str

    def __str__(self):
        return f"[step {self.step}] {self.code}: {self.message}"


# 每个阶段的预期字段;格式为 (key, type, optional)。
# 在下游代码信任 LLM 输出之前先校验形状,防止幻觉字段污染入库数据
SCHEMA_CLASSIFY = [("category", str, False), ("scope", str, False)]
SCHEMA_EXTRACT = [("title", str, False), ("priority", str, False), ("module", str, False)]
SCHEMA_GENERATE = [
    ("repro_steps", str, True),
    ("expected_behavior", str, True),
    ("labels", list, True),
    ("follow_up_questions", list, True),
]

SCHEMA_ONESHOT = [
    ("title", str, False),
    # description 在 chat 路径下用作"用户原话/可改写的描述文本", 服务端再拼接环境提示 + 截图.
    # 旧 oneshot/revise 路径未让 LLM 输出该字段, 缺失时 _validate_shape 会回落为空串.
    ("description", str, True),
    ("priority", str, False),
    ("module", str, False),
    ("repro_steps", str, True),
    ("expected_behavior", str, True),
    ("labels", list, True),
    ("follow_up_questions", list, True),
    ("inferred_env", str, True),
]

ONESHOT_TIMEOUT_SECONDS = 25
ONESHOT_RETRY_COUNT = 1   # one retry on bad JSON (total 2 attempts)

MAX_IMAGES = 3
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB — 与 DashScope qwen-vl-max 实测安全上限对齐;
# 之前 2MB 太苛刻, 4K/Retina 屏截图普遍超过, 被静默丢导致 LLM "看不到截图"

ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3"}


def _read_attachment_bytes(file_key: str) -> bytes:
    """Module-level indirection so tests can patch the storage read."""
    from apps.tools.storage import read_object
    return read_object(file_key)


# 与 AiWizardService._assemble_description 配对: 那边以 "\n\n" 拼接, 这里按 "\n\n"
# 切回去剥离 env blockquote + 图片 markdown. 不能改 raw 用户文本的 "\n\n" 段落分隔.
_ENV_BLOCK_PREFIX = "> 🤖 *AI 推断环境*:"
_IMG_LINE_RE = re.compile(r"^!\[[^\]]*\]\([^)]+\)\s*$")


def _strip_assembled_blocks(desc: str) -> str:
    """Drop the server-appended `> 🤖 AI 推断环境` 和 `![](url)` 块, 还原成纯文本.

    服务端在 description 末尾追加这些块仅是渲染所需; LLM 在下一轮的 history 里
    若看到这些块, 会照搬进自己的 description 输出, 拼装时会被再追加一次 (双图 #bug).
    """
    if not desc:
        return ""
    blocks = desc.split("\n\n")
    kept = [
        b for b in blocks
        if not (b.startswith(_ENV_BLOCK_PREFIX) or _IMG_LINE_RE.match(b.strip()))
    ]
    return "\n\n".join(kept).rstrip()


def _sanitize_messages_for_llm(messages: list[dict]) -> list[dict]:
    """Return a copy of `messages` with prior draft 的 description 还原成 raw 文本.

    只动 assistant draft 消息 — 其它消息原样传过去.
    """
    out: list[dict] = []
    for m in messages:
        if m.get("role") != "assistant":
            out.append(m)
            continue
        content = m.get("content") or ""
        try:
            obj = json.loads(content)
        except (ValueError, TypeError):
            out.append(m)
            continue
        if isinstance(obj, dict) and obj.get("action") == "draft":
            desc = obj.get("description")
            if isinstance(desc, str) and desc:
                obj = {**obj, "description": _strip_assembled_blocks(desc)}
                m = {**m, "content": json.dumps(obj, ensure_ascii=False)}
        out.append(m)
    return out


def _validate_shape(step: int, slug: str, data, schema):
    """Validate parsed LLM output against expected shape.

    - Required field missing or wrong type → raise AiWizardError.
    - Optional field missing or wrong type → coerce to default. LLMs occasionally
      emit `follow_up_questions: null` or `labels: "..."` instead of a list; we
      shouldn't abort the whole wizard over a recoverable optional field.
    """
    if not isinstance(data, dict):
        raise AiWizardError(step=step, code="llm_bad_shape", message=f"{slug} 返回非对象")
    for key, expected_type, optional in schema:
        if key not in data or not isinstance(data[key], expected_type):
            if optional:
                data[key] = "" if expected_type is str else (expected_type())
                continue
            raise AiWizardError(
                step=step, code="llm_bad_shape",
                message=(
                    f"{slug} 缺少字段 {key}" if key not in data
                    else f"{slug} 字段 {key} 类型错误（期望 {expected_type.__name__}）"
                ),
            )
    return data


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

        config = prompt.llm_config

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
        result = self._run_prompt(step=1, slug="wizard_classify", description=description)
        return _validate_shape(1, "wizard_classify", result, SCHEMA_CLASSIFY)

    def extract(self, description: str, classify: dict, modules: list) -> dict:
        result = self._run_prompt(
            step=2,
            slug="wizard_extract",
            description=description,
            classify_json=json.dumps(classify, ensure_ascii=False),
            modules_json=json.dumps(modules, ensure_ascii=False),
        )
        result = _validate_shape(2, "wizard_extract", result, SCHEMA_EXTRACT)
        # 将 priority 限定在合法集合,默认 P2
        if result.get("priority") not in ALLOWED_PRIORITIES:
            result["priority"] = "P2"
        # 截断 title 以避免幻觉超长字符串
        result["title"] = (result.get("title") or "")[:200]
        # module 必须是字符串,且限定在已知模块列表 (或退回到"其他")
        mod = result.get("module") or ""
        if modules and mod not in modules:
            mod = "其他" if "其他" in modules else (modules[0] if modules else "")
        result["module"] = mod
        return result

    def generate(self, description: str, classify: dict, extract: dict, labels: list) -> dict:
        result = self._run_prompt(
            step=3,
            slug="wizard_generate",
            description=description,
            classify_json=json.dumps(classify, ensure_ascii=False),
            extract_json=json.dumps(extract, ensure_ascii=False),
            labels_json=json.dumps(labels, ensure_ascii=False),
        )
        result = _validate_shape(3, "wizard_generate", result, SCHEMA_GENERATE)
        # 过滤 labels 到已知集合,最多 3 个
        raw_labels = result.get("labels") or []
        if not isinstance(raw_labels, list):
            raw_labels = []
        valid_set = set(labels)
        result["labels"] = [l for l in raw_labels if isinstance(l, str) and l in valid_set][:3]
        # 限制追问数量与单条长度
        raw_q = result.get("follow_up_questions") or []
        if not isinstance(raw_q, list):
            raw_q = []
        result["follow_up_questions"] = [str(q)[:100] for q in raw_q if q][:3]
        # 截断长字符串
        result["repro_steps"] = (result.get("repro_steps") or "")[:2000]
        result["expected_behavior"] = (result.get("expected_behavior") or "")[:500]
        return result

    def oneshot_revise(
        self,
        current_draft: dict,
        instruction: str,
        images: list[tuple[str, bytes]],
    ) -> dict:
        """Single multimodal LLM call that either (a) returns an updated draft
        based on the user instruction, or (b) signals 'submit' when the user
        is just confirming the existing draft (e.g. "OK"/"好的"/"提交吧")。

        Return shape:
          - {"action": "submit"}                        when LLM classifies as confirm
          - {"action": "update", ...draft fields}       when LLM revised the draft

        Caller (stream_revise) decides which SSE event to emit based on action.
        Frontend's existing 'draft' event handler still works since the update
        case carries all standard draft fields alongside the action tag.

        Retries once on bad JSON; on vision failure falls back to text-only.
        """
        from apps.ai.services import parse_json_response
        from apps.settings.models import SiteSettings

        prompt = Prompt.objects.filter(slug="wizard_revise", is_active=True).first()
        if prompt is None:
            raise AiWizardError(step=1, code="missing_prompt", message="未配置 Prompt: wizard_revise")

        config = prompt.llm_config

        site = SiteSettings.get_solo()
        modules = list(site.modules or [])
        labels_dict = site.labels or {}
        labels_list = list(labels_dict.keys()) if isinstance(labels_dict, dict) else list(labels_dict)

        # 只把白名单字段送给 LLM, 避免前端塞额外噪声 (例如 v 号/版本元数据)
        sanitized = {
            "title": (current_draft.get("title") or "")[:200],
            "priority": current_draft.get("priority") or "P2",
            "module": current_draft.get("module") or "",
            "repro_steps": (current_draft.get("repro_steps") or "")[:2000],
            "expected_behavior": (current_draft.get("expected_behavior") or "")[:500],
            "labels": [l for l in (current_draft.get("labels") or []) if isinstance(l, str)][:10],
            "follow_up_questions": [
                str(q)[:200] for q in (current_draft.get("follow_up_questions") or []) if q
            ][:5],
            "inferred_env": (current_draft.get("inferred_env") or "")[:200],
        }

        try:
            user_prompt = prompt.user_prompt_template.format(
                current_draft_json=json.dumps(sanitized, ensure_ascii=False),
                instruction=instruction,
                modules_json=json.dumps(modules, ensure_ascii=False),
                labels_json=json.dumps(labels_list, ensure_ascii=False),
            )
        except KeyError as e:
            raise AiWizardError(step=1, code="prompt_format_error", message=f"模板缺失变量 {e}")

        client = LLMClient(config)
        vision_warning = None
        attempts_left = ONESHOT_RETRY_COUNT + 1
        current_images = list(images)
        parsed = None

        while attempts_left > 0:
            attempts_left -= 1
            try:
                raw = client.complete_multimodal(
                    model=prompt.llm_model,
                    system_prompt=prompt.system_prompt,
                    user_prompt=user_prompt,
                    images=current_images,
                    temperature=prompt.temperature,
                    timeout=ONESHOT_TIMEOUT_SECONDS,
                )
            except Exception as e:
                if current_images:
                    logger.warning("wizard_revise vision call failed, falling back to text-only: %s", e)
                    vision_warning = "AI 未能读取截图,已基于文字修订"
                    current_images = []
                    attempts_left += 1
                    continue
                logger.warning("wizard_revise LLM call failed: %s", e, exc_info=True)
                raise AiWizardError(step=1, code="llm_call_failed", message="AI 调用失败,请重试")

            try:
                parsed = parse_json_response(raw)
                break
            except (json.JSONDecodeError, ValueError):
                if attempts_left == 0:
                    logger.warning("wizard_revise bad JSON after retries: %r", raw)
                    raise AiWizardError(step=1, code="llm_bad_json", message="AI 返回格式异常,请重试")

        # action 分类: submit 路径直接短路返回, 不走 draft schema 校验
        if isinstance(parsed, dict) and parsed.get("action") == "submit":
            return {"action": "submit"}

        # update 路径 (action 缺失也视为 update, 兼容老 prompt) - 走标准 draft 校验
        if isinstance(parsed, dict):
            parsed.pop("action", None)
        parsed = _validate_shape(1, "wizard_revise", parsed, SCHEMA_ONESHOT)
        self._sanitize_oneshot(parsed, modules, labels_list)
        if vision_warning:
            parsed["follow_up_questions"] = [vision_warning] + list(parsed.get("follow_up_questions") or [])
            parsed["follow_up_questions"] = parsed["follow_up_questions"][:3]
        parsed["action"] = "update"
        return parsed

    def oneshot_draft(self, description: str, images: list[tuple[str, bytes]]) -> dict:
        """Single multimodal LLM call that produces a complete draft.

        Returns the merged shape (title/priority/module/repro_steps/
        expected_behavior/labels/follow_up_questions/inferred_env). On vision
        failure, retries text-only and prepends a follow_up_question warning.
        On bad JSON, retries once.
        """
        from apps.ai.services import parse_json_response
        from apps.settings.models import SiteSettings

        prompt = Prompt.objects.filter(slug="wizard_oneshot", is_active=True).first()
        if prompt is None:
            raise AiWizardError(step=1, code="missing_prompt", message="未配置 Prompt: wizard_oneshot")

        config = prompt.llm_config

        site = SiteSettings.get_solo()
        modules = list(site.modules or [])
        labels_dict = site.labels or {}
        labels_list = list(labels_dict.keys()) if isinstance(labels_dict, dict) else list(labels_dict)

        try:
            user_prompt = prompt.user_prompt_template.format(
                description=description,
                modules_json=json.dumps(modules, ensure_ascii=False),
                labels_json=json.dumps(labels_list, ensure_ascii=False),
            )
        except KeyError as e:
            raise AiWizardError(step=1, code="prompt_format_error", message=f"模板缺失变量 {e}")

        client = LLMClient(config)
        vision_warning = None
        attempts_left = ONESHOT_RETRY_COUNT + 1
        current_images = list(images)
        parsed = None

        while attempts_left > 0:
            attempts_left -= 1
            try:
                raw = client.complete_multimodal(
                    model=prompt.llm_model,
                    system_prompt=prompt.system_prompt,
                    user_prompt=user_prompt,
                    images=current_images,
                    temperature=prompt.temperature,
                    timeout=ONESHOT_TIMEOUT_SECONDS,
                )
            except Exception as e:
                if current_images:
                    logger.warning("wizard_oneshot vision call failed, falling back to text-only: %s", e)
                    vision_warning = "AI 未能读取截图，已基于文字生成"
                    current_images = []
                    # 视觉失败不消耗 JSON 重试预算
                    attempts_left += 1
                    continue
                logger.warning("wizard_oneshot LLM call failed: %s", e, exc_info=True)
                raise AiWizardError(step=1, code="llm_call_failed", message="AI 调用失败，请重试")

            try:
                parsed = parse_json_response(raw)
                break
            except (json.JSONDecodeError, ValueError):
                if attempts_left == 0:
                    logger.warning("wizard_oneshot bad JSON after retries: %r", raw)
                    raise AiWizardError(step=1, code="llm_bad_json", message="AI 返回格式异常，请重试")

        parsed = _validate_shape(1, "wizard_oneshot", parsed, SCHEMA_ONESHOT)
        self._sanitize_oneshot(parsed, modules, labels_list)
        if vision_warning:
            parsed["follow_up_questions"] = [vision_warning] + list(parsed.get("follow_up_questions") or [])
            parsed["follow_up_questions"] = parsed["follow_up_questions"][:3]
        return parsed

    @staticmethod
    def _sanitize_oneshot(data: dict, modules: list, labels_list: list) -> None:
        """In-place validation per spec §5.4."""
        title = (data.get("title") or "").strip()[:200]
        if not title:
            raise AiWizardError(step=1, code="llm_bad_shape", message="title 为空")
        data["title"] = title

        if data.get("priority") not in ALLOWED_PRIORITIES:
            data["priority"] = "P2"

        mod = (data.get("module") or "").strip()
        if modules and mod not in modules:
            mod = "其他" if "其他" in modules else modules[0]
        data["module"] = mod

        data["repro_steps"] = (data.get("repro_steps") or "")[:2000]
        data["expected_behavior"] = (data.get("expected_behavior") or "")[:500]
        data["inferred_env"] = (data.get("inferred_env") or "")[:200]

        raw_labels = data.get("labels") or []
        if not isinstance(raw_labels, list):
            raw_labels = []
        valid = set(labels_list)
        data["labels"] = [l for l in raw_labels if isinstance(l, str) and l in valid][:3]

        raw_q = data.get("follow_up_questions") or []
        if not isinstance(raw_q, list):
            raw_q = []
        data["follow_up_questions"] = [str(q)[:100] for q in raw_q if q][:3]

    def _load_image_attachments(self, attachment_ids: list, owner) -> list[tuple[str, bytes]]:
        """Backward-compat shim - 旧路径继续用, 不带 warning 信号."""
        images, _ = self._load_image_attachments_with_warnings(attachment_ids, owner)
        return images

    def _load_image_attachments_with_warnings(
        self, attachment_ids: list, owner,
    ) -> tuple[list[tuple[str, bytes]], list[str]]:
        """Resolve attachment_ids → ([(mime, bytes), ...], [user-facing warnings, ...]).

        过滤规则:
          - 仅 image/* mime
          - 仅 owner 自己上传的附件 (防 IDOR; LLM 输出会回到 SSE 流中)
          - 超过 MAX_IMAGE_BYTES (10MB) 的图跳过, 并把"xxx.png 超过 10MB"加入 warnings
          - 读取失败的也跳过 + warning
          - 最多 MAX_IMAGES (3) 张; 多余的也算 warning, 提示用户保留前 3 张
        """
        if not attachment_ids or owner is None:
            return [], []

        from apps.tools.models import Attachment

        rows = list(
            Attachment.objects
            .filter(id__in=attachment_ids, mime_type__startswith="image/", uploaded_by=owner)
            .order_by("created_at")
        )

        out: list[tuple[str, bytes]] = []
        warnings: list[str] = []
        mb_cap = MAX_IMAGE_BYTES // (1024 * 1024)
        for att in rows:
            if att.file_size > MAX_IMAGE_BYTES:
                size_mb = att.file_size / (1024 * 1024)
                msg = f"截图「{att.file_name}」({size_mb:.1f}MB) 超过 {mb_cap}MB 上限, AI 无法读取"
                logger.info("wizard skipping oversize image %s (%d bytes)", att.file_name, att.file_size)
                warnings.append(msg)
                continue
            try:
                raw = _read_attachment_bytes(att.file_key)
            except Exception as e:
                logger.warning("wizard could not read attachment %s: %s", att.file_key, e)
                warnings.append(f"截图「{att.file_name}」读取失败, AI 无法看到")
                continue
            out.append((att.mime_type, raw))
            if len(out) >= MAX_IMAGES:
                remaining = len(rows) - rows.index(att) - 1
                if remaining > 0:
                    warnings.append(f"本轮共 {len(rows)} 张图, AI 仅处理前 {MAX_IMAGES} 张")
                break
        return out, warnings

    def stream_draft(self, description: str, project_id=None, attachment_ids=None, user=None):
        """Dispatch on AI_WIZARD_LEGACY: True → v1 3-stage, False → v2 oneshot.

        `user` is the authenticated requester. Required for v2 to scope
        attachment resolution to attachments the user actually owns.
        """
        from django.conf import settings
        if getattr(settings, "AI_WIZARD_LEGACY", False):
            # Legacy path keeps its original signature (description only) —
            # v1 does not accept attachments so no per-user filter is needed.
            yield from self._stream_draft_legacy(description)
        else:
            yield from self._stream_draft_v2(
                description=description,
                project_id=project_id,
                attachment_ids=attachment_ids or [],
                user=user,
            )

    def stream_revise(self, current_draft: dict, instruction: str, attachment_ids=None, user=None):
        """SSE 流式 wrap oneshot_revise - 同步处理两种 action:
          - update: emit ('draft', {...})  与 stream_draft 一致, 前端追加新 draft turn
          - submit: emit ('submit', {})    前端跳过 draft 渲染, 直接触发"提交" 动作

        Events: step(running) → step(done) → draft | submit → done.
                On failure: step(error) + error.
        """
        import time
        t0 = time.monotonic()

        STEP_LABEL = "AI 正在更新草稿"
        yield ("step", {"step": 1, "label": STEP_LABEL, "status": "running"})

        images = self._load_image_attachments(attachment_ids or [], user)

        try:
            result = self.oneshot_revise(current_draft, instruction, images)
        except AiWizardError as e:
            logger.warning(
                "wizard revise AiWizardError code=%s elapsed_ms=%d",
                e.code, int((time.monotonic() - t0) * 1000),
            )
            yield ("step", {"step": 1, "label": STEP_LABEL, "status": "error"})
            yield ("error", {"code": e.code, "message": e.message})
            yield ("done", {})
            return
        except BaseException:
            logger.exception(
                "wizard revise unexpected failure elapsed_ms=%d",
                int((time.monotonic() - t0) * 1000),
            )
            yield ("step", {"step": 1, "label": STEP_LABEL, "status": "error"})
            yield ("error", {"code": "llm_call_failed", "message": "AI 调用失败,请重试"})
            yield ("done", {})
            return

        # action=submit 短路: AI 判定用户在确认, 直接发 submit 信号
        if result.get("action") == "submit":
            logger.info("wizard revise → submit elapsed_ms=%d", int((time.monotonic() - t0) * 1000))
            yield ("step", {"step": 1, "label": "✓ 已确认提交", "status": "done"})
            yield ("submit", {})
            yield ("done", {})
            return

        # action=update: 走 draft 路径 (这一段是纯 dict 操作, 不会抛 AiWizardError)
        image_meta = self._load_image_metadata(attachment_ids or [], user)
        draft = dict(result)
        draft.pop("action", None)
        draft["description"] = self._assemble_revise_description(
            current_draft.get("description", ""), draft.get("inferred_env", ""), image_meta,
        )

        logger.info("wizard revise ok elapsed_ms=%d", int((time.monotonic() - t0) * 1000))
        yield ("step", {"step": 1, "label": STEP_LABEL, "status": "done"})
        yield ("draft", draft)
        yield ("done", {})

    @staticmethod
    def _assemble_revise_description(prev_description: str, inferred_env: str, image_meta: list | None = None) -> str:
        """修订路径: 保留上一份 description 的主体, 仅追加用户本轮上传的新图片链接。

        若 prev_description 已经含同 URL 的图片标记, 不再重复追加 (用 URL 子串判断,
        简单粗暴但够用; 真正去重还得解析 markdown, 不值)。
        """
        base = (prev_description or "").rstrip()
        parts: list[str] = [base] if base else []
        for att in image_meta or []:
            name = att.get("file_name") or "image"
            url = att.get("file_url") or ""
            if url and url not in base:
                parts.append(f"![{name}]({url})")
        return "\n\n".join(parts)

    def _stream_draft_v2(self, description: str, project_id, attachment_ids: list | None = None, user=None):
        """v2 generator yielding (event_name, payload) for the SSE layer.

        Single LLM call (oneshot multimodal draft). Issue-content-unrelated
        side-effects — auto-assign, future enrichment — are deferred to Celery
        tasks fired from POST /api/issues/, on the principle that the submitter
        only cares whether the AI draft matches their intent, not who handles
        the issue afterwards.

        Events: step(running) → step(done) + draft → done.
                On failure: step(error) + error.
        """
        import time
        t0 = time.monotonic()

        STEP_LABEL = "理解描述与截图"
        yield ("step", {"step": 1, "label": STEP_LABEL, "status": "running"})

        images = self._load_image_attachments(attachment_ids or [], user)

        try:
            draft = self.oneshot_draft(description, images)
            image_meta = self._load_image_metadata(attachment_ids or [], user)
            draft["description"] = self._assemble_description(
                description, draft.get("inferred_env", ""), image_meta,
            )
        except AiWizardError as e:
            logger.warning(
                "wizard oneshot AiWizardError code=%s elapsed_ms=%d",
                e.code, int((time.monotonic() - t0) * 1000),
            )
            yield ("step", {"step": 1, "label": STEP_LABEL, "status": "error"})
            yield ("error", {"code": e.code, "message": e.message})
            yield ("done", {})
            return
        except BaseException:
            logger.exception(
                "wizard oneshot unexpected failure elapsed_ms=%d",
                int((time.monotonic() - t0) * 1000),
            )
            yield ("step", {"step": 1, "label": STEP_LABEL, "status": "error"})
            yield ("error", {"code": "llm_call_failed", "message": "AI 调用失败，请重试"})
            yield ("done", {})
            return

        logger.info("wizard oneshot ok elapsed_ms=%d", int((time.monotonic() - t0) * 1000))
        yield ("step", {"step": 1, "label": STEP_LABEL, "status": "done"})
        yield ("draft", draft)
        yield ("done", {})

    @staticmethod
    def _assemble_description(user_description: str, inferred_env: str, image_meta: list | None = None) -> str:
        """Server-side description assembly per spec §4.3.

        Order: raw user description → inferred_env blockquote → image markdown.
        Each block separated by a blank line. Image attachments are embedded as
        ![name](file_url) so the issue body previews inline (fixes Bug 1).
        """
        raw = (user_description or "").rstrip()
        env = (inferred_env or "").strip()
        parts: list[str] = []
        if raw:
            parts.append(raw)
        if env:
            parts.append(f"> 🤖 *AI 推断环境*: {env}")
        for att in image_meta or []:
            name = att.get("file_name") or "image"
            url = att.get("file_url") or ""
            if url:
                parts.append(f"![{name}]({url})")
        return "\n\n".join(parts)

    def _load_image_metadata(self, attachment_ids: list, owner) -> list[dict]:
        """Return image attachment metadata (file_name, file_url) for inline markdown.

        Separate from _load_image_attachments which reads raw bytes for the
        vision LLM call — this one only needs the URL for the markdown.

        Also scoped to owner=uploaded_by, mirroring _load_image_attachments;
        otherwise an attacker could inline another user's image URL into the
        new Issue's description.
        """
        if not attachment_ids or owner is None:
            return []
        from apps.tools.models import Attachment
        return list(
            Attachment.objects
            .filter(id__in=attachment_ids, mime_type__startswith="image/", uploaded_by=owner)
            .order_by("created_at")
            .values("file_name", "file_url")
        )

    def _stream_draft_legacy(self, description: str):
        """Generator yielding (event_name, data_dict) tuples for the SSE layer.

        Yields ('_heartbeat', None) between stages so the view layer can detect
        client disconnect via BrokenPipeError before incurring the next LLM call.

        Events:
          ("step", {...}) ("draft", {...}) ("done", {})
          ("error", {...}) on failure
          ("_heartbeat", None) — internal signaling, view converts to SSE comment
        """
        from apps.settings.models import SiteSettings

        site = SiteSettings.get_solo()
        modules = list(site.modules or [])
        labels_dict = site.labels or {}
        labels_list = list(labels_dict.keys()) if isinstance(labels_dict, dict) else list(labels_dict)

        try:
            classify = self.classify(description)
            yield ("step", {
                "step": 1,
                "label": "识别问题类型与影响范围",
                "status": "done",
                "result": classify,
            })
            yield ("_heartbeat", None)

            extract = self.extract(description, classify, modules)
            yield ("step", {
                "step": 2,
                "label": "提取关键字段",
                "status": "done",
                "result": extract,
            })
            yield ("_heartbeat", None)

            generate = self.generate(description, classify, extract, labels_list)
            yield ("step", {
                "step": 3,
                "label": "生成复现步骤与预期行为",
                "status": "done",
                "result": generate,
            })

            yield ("draft", self._merge(description, classify, extract, generate))
            yield ("done", {})

        except AiWizardError as e:
            yield ("error", {"step": e.step, "code": e.code, "message": e.message})

    def _merge(self, description: str, classify: dict, extract: dict, generate: dict) -> dict:
        return {
            "title": extract.get("title", ""),
            "description": description,  # client decides whether to use AI-rephrased or raw input
            "repro_steps": generate.get("repro_steps", ""),
            "expected_behavior": generate.get("expected_behavior", ""),
            "priority": extract.get("priority", "P2"),
            "module": extract.get("module", ""),
            "labels": generate.get("labels", []),
            "follow_up_questions": generate.get("follow_up_questions", []),
            "environment": None,
        }

# ============================================================================
# Conversational chat (wizard_chat) - multi-turn dialog with persistent context
# ============================================================================

CHAT_TIMEOUT_SECONDS = 25
CHAT_MAX_TURNS = 10            # 客户端送来的 messages 多于这个值就截掉最早的
CHAT_MAX_CONTENT_LEN = 4000    # 单条 message content 上限 (与 description 限制对齐)

# action=draft 的 schema 与 oneshot 一致 (去掉 action 字段后)
SCHEMA_CHAT_DRAFT = SCHEMA_ONESHOT


def _truncate_messages(messages: list[dict]) -> list[dict]:
    """保留最新 CHAT_MAX_TURNS * 2 条 message (一来一回算一轮)。
    若超长, 从最早的开始丢, 保证开头仍是 user (LLM 不接受首条 assistant)。"""
    cap = CHAT_MAX_TURNS * 2
    if len(messages) <= cap:
        return list(messages)
    trimmed = messages[-cap:]
    # 若首条是 assistant, 再丢一条 (LLM 协议要求首条 user)
    while trimmed and trimmed[0].get("role") != "user":
        trimmed.pop(0)
    return trimmed


def _validate_client_messages(messages) -> list[dict]:
    """client 送来的 messages 严格校验:
      - 必须是 list, 非空, 最后一条必须是 user
      - 每条 {role: user|assistant, content: str}
      - content 长度上限
    返回深拷贝 + 截断后的 messages, 抛 ValueError 让上游转 400。
    """
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages 必须是非空数组")
    out = []
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            raise ValueError(f"messages[{i}] 必须是对象")
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant"):
            raise ValueError(f"messages[{i}].role 必须是 user 或 assistant")
        if not isinstance(content, str):
            raise ValueError(f"messages[{i}].content 必须是字符串")
        if len(content) > CHAT_MAX_CONTENT_LEN:
            raise ValueError(f"messages[{i}].content 超长 (上限 {CHAT_MAX_CONTENT_LEN})")
        out.append({"role": role, "content": content})
    if out[-1].get("role") != "user":
        raise ValueError("messages 最后一条必须是 user")
    return _truncate_messages(out)


class AiChatService:
    """对话式 issue 创建 - wizard_chat prompt。

    - chat(): 单次 LLM 调用, 返回解析后的 {action: draft|submit|ask, ...}
    - stream_chat(): SSE 包装, 把 chat 结果按 action 分别 emit 不同事件
    """

    def chat(
        self,
        messages: list[dict],
        attachment_ids: list,
        user,
        conversation_attachment_ids: list | None = None,
        project=None,
    ) -> dict:
        """单次多轮对话调用。

        - messages: 已校验+截断的 [{role, content}, ...] 历史
        - attachment_ids: 用户本轮 (最新 user message) 附带的图片 ID
        - user: 调用者 (用于 attachment owner 校验)

        返回值 examples:
          {"action": "draft", "title": "...", ...}
          {"action": "ask",   "question": "..."}
          {"action": "submit"}
        失败抛 AiWizardError 让 SSE 层 emit error 事件。
        """
        from apps.ai.services import parse_json_response
        from apps.settings.models import SiteSettings

        prompt = Prompt.objects.filter(slug="wizard_chat", is_active=True).first()
        if prompt is None:
            raise AiWizardError(step=1, code="missing_prompt", message="未配置 Prompt: wizard_chat")

        config = prompt.llm_config

        site = SiteSettings.get_solo()
        modules = list(site.modules or [])
        labels_dict = site.labels or {}
        labels_list = list(labels_dict.keys()) if isinstance(labels_dict, dict) else list(labels_dict)

        # system_prompt 末尾追加项目元数据 (项目名 + 可选模块/标签) - 让 LLM 即使在 messages
        # 被 checkpoint 清空后, 也能从 system prompt 知道"用户当前在哪个项目下创建 issue".
        # 没有这一段, LLM 在新会话首轮会反复问"是哪个项目?"
        project_block = ""
        if project is not None:
            proj_name = getattr(project, "name", "") or ""
            proj_desc = (getattr(project, "description", "") or "").strip()
            if proj_name:
                project_block = f"当前项目: {proj_name}"
                if proj_desc:
                    # 截短防 prompt 膨胀; 200 字够说明项目背景了
                    project_block += f"\n项目说明: {proj_desc[:200]}"
                project_block += "\n"
        try:
            extra_context = prompt.user_prompt_template.format(
                modules_json=json.dumps(modules, ensure_ascii=False),
                labels_json=json.dumps(labels_list, ensure_ascii=False),
            )
        except KeyError as e:
            raise AiWizardError(step=1, code="prompt_format_error", message=f"模板缺失变量 {e}")
        system_prompt = f"{prompt.system_prompt}\n\n---\n{project_block}{extra_context}"

        # 历史 assistant draft 的 description 是服务端拼装结果 (含 env blockquote + 图片 markdown);
        # 直接喂回 LLM 会让它照搬这些块进新输出, 拼装时再被追加一次 → 双图. 先剥成 raw.
        messages = _sanitize_messages_for_llm(messages)

        # 加载本轮图片 (只挂到最后一条 user message 上)
        # 内部方法仍在 AiWizardService 上 — 复用免重写
        helper = AiWizardService()
        images, image_warnings = helper._load_image_attachments_with_warnings(attachment_ids or [], user)

        client = LLMClient(config)
        vision_warning = None
        attempts_left = ONESHOT_RETRY_COUNT + 1
        current_images = list(images)
        parsed = None

        while attempts_left > 0:
            attempts_left -= 1
            try:
                raw = client.chat(
                    model=prompt.llm_model,
                    system_prompt=system_prompt,
                    messages=messages,
                    last_user_images=current_images,
                    temperature=prompt.temperature,
                    timeout=CHAT_TIMEOUT_SECONDS,
                )
            except Exception as e:
                if current_images:
                    logger.warning("wizard_chat vision call failed, falling back to text-only: %s", e)
                    vision_warning = "AI 未能读取截图,已基于文字继续"
                    current_images = []
                    attempts_left += 1
                    continue
                logger.warning("wizard_chat LLM call failed: %s", e, exc_info=True)
                raise AiWizardError(step=1, code="llm_call_failed", message="AI 调用失败,请重试")

            try:
                parsed = parse_json_response(raw)
                break
            except (json.JSONDecodeError, ValueError):
                if attempts_left == 0:
                    logger.warning("wizard_chat bad JSON after retries: %r", raw)
                    raise AiWizardError(step=1, code="llm_bad_json", message="AI 返回格式异常,请重试")

        if not isinstance(parsed, dict):
            raise AiWizardError(step=1, code="llm_bad_shape", message="AI 返回非对象")

        # 合并所有 warning 信号 (尺寸/读取失败/视觉调用失败回退)
        warnings_to_user = list(image_warnings)
        if vision_warning:
            warnings_to_user.append(vision_warning)

        action = parsed.get("action")
        if action == "submit":
            return {"action": "submit", "_warnings": warnings_to_user}
        if action == "ask":
            question = (parsed.get("question") or "").strip()[:200]
            if not question:
                raise AiWizardError(step=1, code="llm_bad_shape", message="ask 缺少 question 字段")
            return {"action": "ask", "question": question, "_warnings": warnings_to_user}

        # action == "draft" 或缺失 (兼容: 缺失视为 draft)
        parsed.pop("action", None)
        parsed = _validate_shape(1, "wizard_chat", parsed, SCHEMA_CHAT_DRAFT)
        helper._sanitize_oneshot(parsed, modules, labels_list)
        if vision_warning:
            parsed["follow_up_questions"] = [vision_warning] + list(parsed.get("follow_up_questions") or [])
            parsed["follow_up_questions"] = parsed["follow_up_questions"][:3]
        # 拼装 description: LLM 输出的 description (用户可让它改写) + AI 推断环境 + 全对话累计图片 markdown.
        # LLM 没给 description (旧 prompt / 漏字段) 时回落到首条 user 消息, 保住向后兼容.
        # 用 conversation_attachment_ids 而非 attachment_ids - 否则当 LLM 先 ask 再 draft 时,
        # 用户回答那一轮 attachment_ids=[], 早先附的图就丢了 (#bug)
        llm_desc = (parsed.get("description") or "").strip()
        if not llm_desc:
            for m in messages:
                if m.get("role") == "user":
                    llm_desc = m.get("content") or ""
                    break
        meta_ids = conversation_attachment_ids if conversation_attachment_ids is not None else attachment_ids
        image_meta = helper._load_image_metadata(meta_ids or [], user)
        parsed["description"] = helper._assemble_description(
            llm_desc, parsed.get("inferred_env", ""), image_meta,
        )
        parsed["action"] = "draft"
        parsed["_warnings"] = warnings_to_user
        return parsed

    def stream_chat(
        self,
        messages: list[dict],
        attachment_ids: list | None = None,
        user=None,
        conversation_attachment_ids: list | None = None,
        project=None,
    ):
        """SSE 流式 wrap chat() - 按 action 分发事件:
          - draft  → emit ('draft', {title, priority, ...})
          - ask    → emit ('ask',   {question})
          - submit → emit ('submit', {})

        额外的 dup 事件 (仅首份 draft, 受 settings.WIZARD_CHAT_DUP_CHECK_ENABLED 控制):
          - dup    → emit ('dup', {candidates: [{id, title, status, reason}, ...]})

        失败时 emit ('step', error) + ('error', {code, message}) + ('done', {})
        """
        import time
        t0 = time.monotonic()

        STEP_LABEL = "AI 正在思考"
        yield ("step", {"step": 1, "label": STEP_LABEL, "status": "running"})

        try:
            result = self.chat(
                messages,
                attachment_ids or [],
                user,
                conversation_attachment_ids=conversation_attachment_ids,
                project=project,
            )
        except AiWizardError as e:
            logger.warning(
                "wizard_chat AiWizardError code=%s elapsed_ms=%d",
                e.code, int((time.monotonic() - t0) * 1000),
            )
            yield ("step", {"step": 1, "label": STEP_LABEL, "status": "error"})
            yield ("error", {"code": e.code, "message": e.message})
            yield ("done", {})
            return
        except BaseException:
            logger.exception(
                "wizard_chat unexpected failure elapsed_ms=%d",
                int((time.monotonic() - t0) * 1000),
            )
            yield ("step", {"step": 1, "label": STEP_LABEL, "status": "error"})
            yield ("error", {"code": "llm_call_failed", "message": "AI 调用失败,请重试"})
            yield ("done", {})
            return

        action = result.get("action")
        elapsed = int((time.monotonic() - t0) * 1000)

        # 提取 chat() 顺带返回的 vision warning, 在终态事件之前 emit, 让前端把它显示给用户
        warnings_to_user = result.pop("_warnings", None) or []
        for warning_msg in warnings_to_user:
            yield ("warning", {"message": warning_msg})

        if action == "submit":
            logger.info("wizard_chat → submit elapsed_ms=%d", elapsed)
            yield ("step", {"step": 1, "label": "✓ 已确认提交", "status": "done"})
            yield ("submit", {})
            yield ("done", {})
            return
        if action == "ask":
            logger.info("wizard_chat → ask elapsed_ms=%d", elapsed)
            yield ("step", {"step": 1, "label": "AI 需要补充信息", "status": "done"})
            yield ("ask", {"question": result["question"]})
            yield ("done", {})
            return

        # draft
        logger.info("wizard_chat → draft elapsed_ms=%d", elapsed)
        draft = dict(result)
        draft.pop("action", None)
        # description 已在 chat() 内拼装好 (含原始用户描述 + AI 推断环境 + 本轮图片 markdown)
        yield ("step", {"step": 1, "label": STEP_LABEL, "status": "done"})
        yield ("draft", draft)

        # 仅首份 draft 跑一次重复检测; revise 路径用户已表明要新建, 不再骚扰。
        # 关闭方式: env WIZARD_CHAT_DUP_CHECK_ENABLED=0 (重启) 或 把 issue_duplicate_check
        # prompt is_active 改 false (热切换, 不用重启)
        from django.conf import settings as _settings
        if (
            getattr(_settings, "WIZARD_CHAT_DUP_CHECK_ENABLED", True)
            and project is not None
            and self._is_first_draft(messages)
            and draft.get("title")
        ):
            from .services import check_duplicates
            try:
                project_id = project.id if hasattr(project, "id") else int(project)
                candidates = check_duplicates(
                    project_id, draft["title"], draft.get("description", ""),
                )
            except Exception:
                logger.exception("wizard_chat dup-check failed; skipping")
                candidates = []
            if candidates:
                yield ("dup", {"candidates": candidates})

        yield ("done", {})

    @staticmethod
    def _is_first_draft(messages: list[dict]) -> bool:
        """messages 里如果已经有 assistant 返回过 draft, 当前就是 revise, 跳过 dup-check"""
        for m in messages:
            if m.get("role") == "assistant" and '"action":"draft"' in (m.get("content") or ""):
                return False
        return True
