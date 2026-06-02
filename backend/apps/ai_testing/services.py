from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

import apps.tools.storage as tools_storage
from apps.ai.client import LLMClient
from apps.ai.models import LLMConfig
from apps.ai.services import parse_json_response
from apps.issues.services import create_issue
from apps.settings.models import SiteSettings
from apps.tools.models import Attachment

from .agent import AITestAgent, AgentDecision
from .browser import (
    BrowserRuntimeUnavailable,
    BrowserToolResult,
    HeadlessBrowserSession,
)
from .models import AITestingModelSettings, BrowserArtifact, TestFlow, TestRun, TestStepRun
from .prompts import (
    ISSUE_WRITER_SYSTEM_PROMPT,
    REVIEWER_SYSTEM_PROMPT,
    build_issue_writer_user_prompt,
    build_reviewer_user_prompt,
)

logger = logging.getLogger(__name__)

DEFAULT_LOGIN_ENTRY_TARGET = (
    'css=a[href*="/login"], button:has-text("登录"), [role="button"]:has-text("登录"), '
    'button:has-text("Login"), [role="button"]:has-text("Login")'
)
DEFAULT_USERNAME_TARGET = (
    'css=input[name="username"], input[name="account"], input[name="email"], input[name="mobile"], '
    'input[id*="user" i], input[id*="account" i], input[id*="email" i], input[autocomplete="username"], '
    'input[placeholder*="用户名"], input[placeholder*="账号"], input[placeholder*="邮箱"], '
    'input[type="email"], input[type="text"]'
)
DEFAULT_PASSWORD_TARGET = (
    'css=input[type="password"], input[name="password"], input[name="passwd"], input[name="pwd"], '
    'input[id*="pass" i], input[autocomplete="current-password"], input[autocomplete="new-password"], '
    'input[placeholder*="密码"], input[placeholder*="Password"]'
)
DEFAULT_SUBMIT_TARGET = 'css=button[type="submit"], input[type="submit"], button:has-text("登录"), [role="button"]:has-text("登录")'
DEFAULT_LOGIN_PATH = "/login"
LOOP_GUARD_THRESHOLD = 3
LOOP_GUARD_OBSERVE_MAX_TEXT = 1800
LOOP_GUARD_OBSERVE_MAX_ELEMENTS = 80
LOOP_GUARD_TOOLS = {"click", "fill", "press", "wait_for_text", "assert_text"}
CONFIRM_GUARD_OBSERVE_MAX_TEXT = 2200
CONFIRM_GUARD_OBSERVE_MAX_ELEMENTS = 120
DISMISS_ACTION_TOKENS = (
    "close",
    "cancel",
    "discard",
    "leave",
    "exit",
    "关闭",
    "取消",
    "放弃",
    "离开",
    "退出",
    "返回",
)


@dataclass
class SuggestedIssuePayload:
    project_id: int
    title: str
    description: str
    priority: str
    source: str
    source_meta: dict


def build_failed_run_issue_payload(*, run_id: int, project_id: int, run_name: str, status: str, summary: str) -> SuggestedIssuePayload:
    return SuggestedIssuePayload(
        project_id=project_id,
        title=f"[AI测试失败] {run_name}",
        description=summary,
        priority="P2",
        source="ai_testing",
        source_meta={"test_run_id": run_id, "status": status},
    )


def _pick_default_labels() -> list[str]:
    labels = SiteSettings.get_solo().labels
    if isinstance(labels, dict) and "AI测试" in labels:
        return ["AI测试"]
    if isinstance(labels, list) and "AI测试" in labels:
        return ["AI测试"]
    return []


def _build_run_failure_description(run: TestRun) -> str:
    lines = [
        f"测试执行 ID: {run.id}",
        f"执行名称: {run.name}",
        f"执行状态: {run.status}",
        f"目标地址: {run.target_url or '-'}",
        f"环境: {run.environment.name} ({run.environment.base_url})",
        "",
        "失败原因:",
        run.failure_reason or "未记录",
        "",
        "最终摘要:",
        run.final_summary or "未记录",
    ]
    steps = run.steps.order_by("step_index", "id")[:8]
    if steps:
        lines.extend(["", "关键步骤:"])
        for step in steps:
            lines.append(
                f"{step.step_index}. {step.tool_name} [{step.status}] {step.error_message or ''}".strip()
            )
    return "\n".join(lines)


def create_issue_for_failed_run(*, run: TestRun, actor):
    if run.status not in {TestRun.STATUS_FAILED, TestRun.STATUS_TIMEOUT, TestRun.STATUS_CANCELLED}:
        raise ValueError("仅失败/超时/取消的执行可以创建问题")

    payload = build_failed_run_issue_payload(
        run_id=run.id,
        project_id=run.project_id,
        run_name=run.name,
        status=run.status,
        summary=_build_run_failure_description(run),
    )
    issue = create_issue(
        project=run.project,
        actor=actor,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        source=payload.source,
        source_meta={
            **payload.source_meta,
            "environment_id": run.environment_id,
            "flow_id": run.flow_id,
        },
        labels=_pick_default_labels(),
        reporter="",
    )
    return issue


def _pick_runtime_model_settings(run: TestRun) -> AITestingModelSettings | None:
    if run.environment.model_settings_id:
        return run.environment.model_settings
    return (
        AITestingModelSettings.objects.select_related("llm_config")
        .filter(is_global_default=True)
        .first()
    )


def _pick_llm_config(model_settings: AITestingModelSettings | None) -> LLMConfig | None:
    if model_settings and model_settings.llm_config_id:
        return model_settings.llm_config
    return (
        LLMConfig.objects.filter(is_active=True, is_default=True).first()
        or LLMConfig.objects.filter(is_active=True).first()
    )


def _pick_planner_model(model_settings: AITestingModelSettings | None, llm_config: LLMConfig | None) -> str:
    if model_settings and model_settings.planner_model:
        return model_settings.planner_model
    if llm_config and llm_config.available_models:
        return llm_config.available_models[0]
    return ""


def _pick_reviewer_model(
    model_settings: AITestingModelSettings | None,
    llm_config: LLMConfig | None,
    planner_model: str,
) -> str:
    if model_settings and model_settings.critic_model:
        return model_settings.critic_model
    if planner_model:
        return planner_model
    if llm_config and llm_config.available_models:
        return llm_config.available_models[0]
    return ""


def _build_seed_actions(run: TestRun, target_url: str) -> list[AgentDecision]:
    flow = run.flow
    env = run.environment
    cfg = env.login_config if isinstance(env.login_config, dict) else {}

    actions: list[AgentDecision] = [AgentDecision("open_url", {"url": target_url}, "打开测试入口")]
    if env.login_type == env.LOGIN_USERNAME_PASSWORD and env.login_username and env.has_login_password:
        login_entry_target = cfg.get("login_entry_target") or DEFAULT_LOGIN_ENTRY_TARGET
        login_url = cfg.get("login_url") or DEFAULT_LOGIN_PATH
        username_target = cfg.get("username_target") or DEFAULT_USERNAME_TARGET
        password_target = cfg.get("password_target") or DEFAULT_PASSWORD_TARGET
        submit_target = cfg.get("submit_target") or DEFAULT_SUBMIT_TARGET
        post_login_wait_text = cfg.get("post_login_wait_text") or ""
        if login_entry_target:
            actions.append(
                AgentDecision(
                    "click",
                    {"target": login_entry_target},
                    "尝试打开登录表单",
                    allow_failure=True,
                )
            )
        if login_url:
            actions.append(
                AgentDecision(
                    "open_url",
                    {"url": login_url},
                    "尝试直接进入登录页面",
                    allow_failure=True,
                )
            )
        actions.extend(
            [
                AgentDecision(
                    "fill",
                    {"target": username_target, "value": env.login_username},
                    "填入测试账号",
                    allow_failure=True,
                ),
                AgentDecision(
                    "fill",
                    {"target": password_target, "value": env.get_login_password()},
                    "填入测试密码",
                    allow_failure=True,
                ),
                AgentDecision(
                    "click",
                    {"target": submit_target},
                    "提交登录",
                    allow_failure=True,
                ),
            ]
        )
        if post_login_wait_text:
            actions.append(
                AgentDecision(
                    "wait_for_text",
                    {"text": post_login_wait_text, "timeout_ms": 15000},
                    "等待登录后关键文本",
                    allow_failure=True,
                )
            )

    if flow and flow.target_url and flow.target_url != target_url:
        actions.append(AgentDecision("open_url", {"url": flow.target_url}, "进入流程起始地址"))
    return actions


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            key = str(k).lower()
            if any(token in key for token in ("password", "token", "secret", "cookie", "authorization", "api_key")):
                out[k] = "***"
            else:
                out[k] = _redact_value(v)
        return out
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value


def _store_screenshot_artifact(
    *,
    run: TestRun,
    step: TestStepRun,
    file_name: str,
    content: bytes,
    mime_type: str = "image/png",
) -> BrowserArtifact | None:
    try:
        upload = SimpleUploadedFile(file_name, content, content_type=mime_type)
        url, key = tools_storage.upload_image(upload)
        attachment = Attachment.objects.create(
            uploaded_by=run.created_by,
            file_name=file_name,
            file_key=key,
            file_url=url,
            file_size=len(content),
            mime_type=mime_type,
            content_hash=hashlib.sha256(content).hexdigest(),
        )
        return BrowserArtifact.objects.create(
            run=run,
            step=step,
            artifact_type=BrowserArtifact.TYPE_SCREENSHOT,
            attachment=attachment,
            metadata={"file_name": file_name},
        )
    except Exception:
        logger.exception("ai-testing screenshot artifact storage failed for run=%s step=%s", run.id, step.id)
        return None


def _store_text_artifact(*, run: TestRun, artifact_type: str, content: str, metadata: dict[str, Any] | None = None):
    if not content.strip():
        return None
    return BrowserArtifact.objects.create(
        run=run,
        artifact_type=artifact_type,
        content=content[:20000],
        metadata=metadata or {},
    )


def _allocate_step_index(run: TestRun, desired_index: int) -> int:
    candidate = max(1, int(desired_index))
    while TestStepRun.objects.filter(run=run, step_index=candidate).exists():
        candidate += 1
    return candidate


def _append_step(
    *,
    run: TestRun,
    step_index: int,
    decision: AgentDecision,
    result: BrowserToolResult,
) -> TestStepRun:
    persisted_index = _allocate_step_index(run, step_index)
    step = TestStepRun.objects.create(
        run=run,
        step_index=persisted_index,
        skill_name="generic_harness",
        thought_summary=decision.thought_summary,
        tool_name=decision.tool_name,
        tool_input=_redact_value(decision.tool_input),
        tool_result=_redact_value(result.data),
        page_url=result.page_url or "",
        status=TestStepRun.STATUS_SUCCESS if result.ok else TestStepRun.STATUS_FAILED,
        error_message="" if result.ok else result.message,
    )
    if result.screenshot:
        _store_screenshot_artifact(
            run=run,
            step=step,
            file_name=result.screenshot.file_name,
            content=result.screenshot.content,
            mime_type=result.screenshot.mime_type,
        )
    return step


def _append_runtime_failure_step(run: TestRun, error_message: str):
    last = TestStepRun.objects.filter(run=run).order_by("-step_index", "-id").first()
    step_index = _allocate_step_index(run, (last.step_index + 1) if last else 1)
    TestStepRun.objects.create(
        run=run,
        step_index=step_index,
        skill_name="system",
        thought_summary="执行器异常",
        tool_name="runtime_error",
        tool_input={},
        tool_result={},
        page_url=run.target_url or "",
        status=TestStepRun.STATUS_FAILED,
        error_message=error_message[:2000],
    )


def _store_runtime_logs(run: TestRun, browser: HeadlessBrowserSession):
    _store_text_artifact(
        run=run,
        artifact_type=BrowserArtifact.TYPE_CONSOLE,
        content="\n".join(f"[{item.get('type', '')}] {item.get('text', '')}" for item in browser.console_logs[-80:]),
        metadata={"log_count": len(browser.console_logs)},
    )
    _store_text_artifact(
        run=run,
        artifact_type=BrowserArtifact.TYPE_NETWORK,
        content="\n".join(
            f"{item.get('method', '')} {item.get('url', '')} :: {item.get('failure', '')}"
            for item in browser.network_errors[-80:]
        ),
        metadata={"error_count": len(browser.network_errors)},
    )


def _summarize_steps_for_expert(run: TestRun, limit: int = 20) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in run.steps.order_by("step_index", "id")[:limit]:
        out.append(
            {
                "step": step.step_index,
                "tool": step.tool_name,
                "status": step.status,
                "thought": (step.thought_summary or "")[:240],
                "error": (step.error_message or "")[:300],
                "url": step.page_url or "",
            }
        )
    return out


def _summarize_artifacts_for_expert(run: TestRun, limit: int = 16) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for artifact in run.artifacts.select_related("step").order_by("-created_at")[:limit]:
        out.append(
            {
                "type": artifact.artifact_type,
                "step": artifact.step.step_index if artifact.step_id else None,
                "content": (artifact.content or "")[:480],
                "has_attachment": bool(artifact.attachment_id),
            }
        )
    return out


def _normalize_priority(value: str | None) -> str:
    raw = (value or "").strip().upper()
    if raw in {"P0", "P1", "P2", "P3"}:
        return raw
    return "P2"


def _run_reviewer_expert(
    *,
    run: TestRun,
    flow: TestFlow | None,
    llm_config: LLMConfig | None,
    reviewer_model: str,
    timeout_secs: int,
    model_settings: AITestingModelSettings | None,
) -> dict[str, Any] | None:
    if not (llm_config and reviewer_model and model_settings and model_settings.enable_critic_review):
        return None

    try:
        steps = _summarize_steps_for_expert(run)
        artifacts = _summarize_artifacts_for_expert(run)
        user_prompt = build_reviewer_user_prompt(
            run_name=run.name,
            flow_description=(flow.description if flow else "") or "",
            success_criteria=(flow.success_criteria if flow else "") or "",
            final_status=run.status,
            final_summary=run.final_summary or "",
            failure_reason=run.failure_reason or "",
            steps=steps,
            artifacts=artifacts,
        )
        raw = LLMClient(llm_config).complete(
            model=reviewer_model,
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=min(0.2, max(0.0, model_settings.temperature)),
            timeout=min(90, timeout_secs),
        )
        payload = parse_json_response(raw)
        verdict = str(payload.get("verdict") or "").strip().lower()
        reason = str(payload.get("reason") or "").strip()[:600]
        confidence_raw = payload.get("confidence")
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.0
        should_create_issue = bool(payload.get("should_create_issue"))
        review = {
            "verdict": verdict if verdict in {"pass", "fail"} else "fail",
            "reason": reason or "评审模型未给出有效结论",
            "confidence": max(0.0, min(confidence, 1.0)),
            "should_create_issue": should_create_issue,
            "priority": _normalize_priority(payload.get("priority")),
            "raw": raw[:2000],
        }
        _store_text_artifact(
            run=run,
            artifact_type=BrowserArtifact.TYPE_CONSOLE,
            content=json.dumps(review, ensure_ascii=False),
            metadata={"kind": "expert_review"},
        )
        return review
    except Exception:
        logger.exception("ai-testing expert review failed for run=%s", run.id)
        return None


def _run_issue_writer_expert(
    *,
    run: TestRun,
    flow: TestFlow | None,
    llm_config: LLMConfig | None,
    reviewer_model: str,
    timeout_secs: int,
    reviewer_reason: str,
) -> dict[str, str]:
    fallback = {
        "title": f"[AI测试失败] {run.name}",
        "description": _build_run_failure_description(run),
        "priority": "P2",
    }
    if not (llm_config and reviewer_model):
        return fallback
    try:
        steps = _summarize_steps_for_expert(run)
        artifacts = _summarize_artifacts_for_expert(run)
        user_prompt = build_issue_writer_user_prompt(
            run_name=run.name,
            target_url=run.target_url or "",
            flow_description=(flow.description if flow else "") or "",
            reviewer_reason=reviewer_reason,
            steps=steps,
            artifacts=artifacts,
        )
        raw = LLMClient(llm_config).complete(
            model=reviewer_model,
            system_prompt=ISSUE_WRITER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
            timeout=min(90, timeout_secs),
        )
        payload = parse_json_response(raw)
        title = str(payload.get("title") or "").strip()[:200] or fallback["title"]
        description = str(payload.get("description") or "").strip() or fallback["description"]
        return {
            "title": title,
            "description": description[:12000],
            "priority": _normalize_priority(payload.get("priority")),
        }
    except Exception:
        logger.exception("ai-testing issue-writer expert failed for run=%s", run.id)
        return fallback


def _auto_create_issue_from_expert(
    *,
    run: TestRun,
    reviewer_reason: str,
    llm_config: LLMConfig | None,
    reviewer_model: str,
    timeout_secs: int,
) -> int | None:
    actor = run.created_by
    if not actor or not actor.has_perm("issues.add_issue"):
        return None
    issue_draft = _run_issue_writer_expert(
        run=run,
        flow=run.flow,
        llm_config=llm_config,
        reviewer_model=reviewer_model,
        timeout_secs=timeout_secs,
        reviewer_reason=reviewer_reason,
    )
    issue = create_issue(
        project=run.project,
        actor=actor,
        title=issue_draft["title"],
        description=issue_draft["description"],
        priority=issue_draft["priority"],
        source="ai_testing",
        source_meta={
            "test_run_id": run.id,
            "status": run.status,
            "environment_id": run.environment_id,
            "flow_id": run.flow_id,
            "generated_by": "issue_writer_expert",
        },
        labels=_pick_default_labels(),
        reporter="",
    )
    return issue.id


def _run_expert_pipeline(
    *,
    run: TestRun,
    flow: TestFlow | None,
    llm_config: LLMConfig | None,
    reviewer_model: str,
    timeout_secs: int,
    model_settings: AITestingModelSettings | None,
):
    review = _run_reviewer_expert(
        run=run,
        flow=flow,
        llm_config=llm_config,
        reviewer_model=reviewer_model,
        timeout_secs=timeout_secs,
        model_settings=model_settings,
    )
    if not review:
        return

    if run.status == TestRun.STATUS_SUCCESS and review["verdict"] == "fail":
        run.status = TestRun.STATUS_FAILED
        run.failure_reason = f"expert_review_failed: {review['reason']}"
        run.final_summary = "专家评审判定失败"

    if run.status in {TestRun.STATUS_FAILED, TestRun.STATUS_TIMEOUT, TestRun.STATUS_CANCELLED}:
        should_create = review["should_create_issue"] and review["verdict"] == "fail"
        issue_id = None
        if should_create:
            issue_id = _auto_create_issue_from_expert(
                run=run,
                reviewer_reason=review["reason"],
                llm_config=llm_config,
                reviewer_model=reviewer_model,
                timeout_secs=timeout_secs,
            )
        if issue_id:
            run.final_summary = f"{run.final_summary or '执行失败'}（已自动创建 Issue #{issue_id}）"
        elif review["reason"]:
            run.final_summary = f"{run.final_summary or '执行结束'}（专家评审：{review['reason'][:160]}）"


def _normalize_inline_text(value: Any, max_len: int = 280) -> str:
    text = " ".join(str(value or "").split())
    return text[:max_len]


def _build_observation_signature(observation: dict[str, Any], *, page_url: str = "") -> str:
    if not isinstance(observation, dict):
        observation = {}
    elements = []
    raw_elements = observation.get("interactive_elements")
    if isinstance(raw_elements, list):
        for item in raw_elements[:12]:
            if not isinstance(item, dict):
                continue
            elements.append(
                {
                    "tag": _normalize_inline_text(item.get("tag"), 40),
                    "id": _normalize_inline_text(item.get("id"), 80),
                    "name": _normalize_inline_text(item.get("name"), 80),
                    "role": _normalize_inline_text(item.get("role"), 80),
                    "type": _normalize_inline_text(item.get("type"), 80),
                    "text": _normalize_inline_text(item.get("text"), 120),
                    "testid": _normalize_inline_text(item.get("testid"), 80),
                }
            )
    normalized = {
        "url": _normalize_inline_text(page_url or observation.get("url"), 280),
        "title": _normalize_inline_text(observation.get("title"), 200),
        "visible_text": _normalize_inline_text(observation.get("visible_text"), 360),
        "unsaved_dialog": _normalize_inline_text(
            (observation.get("unsaved_changes_dialog") or {}).get("dialog_text")
            if isinstance(observation.get("unsaved_changes_dialog"), dict)
            else "",
            200,
        ),
        "elements": elements,
    }
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _extract_action_target(decision: AgentDecision) -> str:
    tool_input = decision.tool_input if isinstance(decision.tool_input, dict) else {}
    for key in ("target", "text", "url", "key"):
        value = tool_input.get(key)
        if value is not None and str(value).strip():
            return _normalize_inline_text(value, 160)
    return ""


def _is_potential_dismiss_action(decision: AgentDecision) -> bool:
    tool_input = decision.tool_input if isinstance(decision.tool_input, dict) else {}
    if decision.tool_name == "press":
        key = _normalize_inline_text(tool_input.get("key"), 80).casefold()
        return key in {"escape", "esc"}
    if decision.tool_name != "click":
        return False
    target = _extract_action_target(decision).casefold()
    if not target:
        return False
    return any(token.casefold() in target for token in DISMISS_ACTION_TOKENS)


def _normalize_click_target(text: str) -> str:
    raw = _normalize_inline_text(text, 120)
    if not raw:
        return ""
    if raw.startswith(("text=", "css=", "xpath=", "//")):
        return raw
    return f"text={raw}"


def _handle_unsaved_confirmation_guard(
    *,
    run: TestRun,
    browser: HeadlessBrowserSession,
    decision: AgentDecision,
    step_index: int,
) -> dict[str, Any] | None:
    if not _is_potential_dismiss_action(decision):
        return None

    observe_decision = AgentDecision(
        "observe_page",
        {
            "max_text": CONFIRM_GUARD_OBSERVE_MAX_TEXT,
            "max_elements": CONFIRM_GUARD_OBSERVE_MAX_ELEMENTS,
        },
        "弹窗保护：检查二次确认框",
    )
    observe_result = browser.execute_tool(observe_decision.tool_name, observe_decision.tool_input)
    _append_step(run=run, step_index=step_index + 1, decision=observe_decision, result=observe_result)
    if not observe_result.ok or not isinstance(observe_result.data, dict):
        return None

    observation = observe_result.data
    signal = observation.get("unsaved_changes_dialog")
    if not isinstance(signal, dict) or not signal.get("detected"):
        return {"observation": observation}

    recover_target_raw = _normalize_inline_text(signal.get("recover_target"), 120) or "继续编辑"
    recover_target = _normalize_click_target(recover_target_raw)
    recover_decision = AgentDecision(
        "click",
        {"target": recover_target},
        "弹窗保护：优先继续编辑，避免内容丢失",
        allow_failure=True,
    )
    recover_result = browser.execute_tool(recover_decision.tool_name, recover_decision.tool_input)
    _append_step(run=run, step_index=step_index + 2, decision=recover_decision, result=recover_result)

    post_observe_decision = AgentDecision(
        "observe_page",
        {
            "max_text": CONFIRM_GUARD_OBSERVE_MAX_TEXT,
            "max_elements": CONFIRM_GUARD_OBSERVE_MAX_ELEMENTS,
        },
        "弹窗保护：处理后复查页面",
    )
    post_observe_result = browser.execute_tool(post_observe_decision.tool_name, post_observe_decision.tool_input)
    _append_step(
        run=run,
        step_index=step_index + 3,
        decision=post_observe_decision,
        result=post_observe_result,
    )
    if post_observe_result.ok and isinstance(post_observe_result.data, dict):
        return {"observation": post_observe_result.data}
    return {"observation": observation}


def _build_repeat_action_key(
    *,
    decision: AgentDecision,
    observation_signature: str,
    page_url: str,
) -> str:
    if decision.tool_name not in LOOP_GUARD_TOOLS:
        return ""
    target = _extract_action_target(decision)
    if not target:
        return ""
    return "|".join(
        [
            decision.tool_name,
            target,
            _normalize_inline_text(page_url, 280),
            observation_signature,
        ]
    )


def execute_ai_test_run(run: TestRun):
    run = TestRun.objects.select_related("flow", "environment", "project").get(pk=run.pk)
    if run.status != TestRun.STATUS_PENDING:
        return run

    flow = run.flow
    env = run.environment
    model_settings = _pick_runtime_model_settings(run)
    llm_config = _pick_llm_config(model_settings)
    planner_model = _pick_planner_model(model_settings, llm_config)
    reviewer_model = _pick_reviewer_model(model_settings, llm_config, planner_model)

    max_steps = flow.max_steps if flow else 30
    max_steps = max(1, min(max_steps, model_settings.max_agent_turns if model_settings else max_steps))
    run_timeout_secs = flow.timeout_secs if flow else 300
    tool_timeout_secs = model_settings.tool_call_timeout_secs if model_settings else 60
    temperature = model_settings.temperature if model_settings else 0.1

    target_url = run.target_url or (flow.target_url if flow else "") or env.base_url
    seed_actions = _build_seed_actions(run, target_url)
    login_hint = ""
    if env.login_type == env.LOGIN_USERNAME_PASSWORD and env.login_username:
        login_hint = (
            f"请使用环境账号 {env.login_username}，密码由系统自动注入，不要记录明文。"
            "系统会先执行登录 seed 步骤；只有在页面明确仍停留登录表单时，才重复登录动作。"
        )

    run.status = TestRun.STATUS_RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at", "updated_at"])

    agent = AITestAgent(
        llm_config=llm_config,
        model=planner_model,
        temperature=temperature,
        timeout_secs=tool_timeout_secs,
        seed_actions=seed_actions,
    )

    history: list[dict[str, Any]] = []
    observation: dict[str, Any] = {}
    observation_signature = _build_observation_signature(observation, page_url=target_url)
    repeat_action_key = ""
    repeat_action_count = 0
    last_result: BrowserToolResult | None = None
    started_monotonic = time.monotonic()

    try:
        with HeadlessBrowserSession(
            base_url=env.base_url,
            allowed_url_patterns=env.allowed_url_patterns or [],
            allow_write_actions=env.allow_write_actions,
            allow_dangerous_actions=env.allow_dangerous_actions,
            timeout_ms=tool_timeout_secs * 1000,
            headless=True,
        ) as browser:
            for step_index in range(1, max_steps + 1):
                run.refresh_from_db(fields=["status"])
                if run.status == TestRun.STATUS_CANCELLED:
                    run.final_summary = "执行被用户取消"
                    run.failure_reason = "cancelled_by_user"
                    run.finished_at = timezone.now()
                    run.save(update_fields=["final_summary", "failure_reason", "finished_at", "updated_at"])
                    return run

                if time.monotonic() - started_monotonic > run_timeout_secs:
                    timeout_step_index = _allocate_step_index(run, step_index)
                    timeout_step = TestStepRun.objects.create(
                        run=run,
                        step_index=timeout_step_index,
                        skill_name="system",
                        thought_summary="执行超时保护触发",
                        tool_name="timeout_guard",
                        tool_input={"run_timeout_secs": run_timeout_secs},
                        tool_result={},
                        page_url=browser.page.url if browser.page else (run.target_url or ""),
                        status=TestStepRun.STATUS_FAILED,
                        error_message=f"执行超时（>{run_timeout_secs}s）",
                    )
                    shot = browser.execute_tool("take_screenshot", {"reason": "timeout", "step_index": step_index})
                    if shot.screenshot:
                        _store_screenshot_artifact(
                            run=run,
                            step=timeout_step,
                            file_name=shot.screenshot.file_name,
                            content=shot.screenshot.content,
                            mime_type=shot.screenshot.mime_type,
                        )
                    run.status = TestRun.STATUS_TIMEOUT
                    run.failure_reason = f"执行超时（>{run_timeout_secs}s）"
                    run.final_summary = "执行超时，已强制结束"
                    run.finished_at = timezone.now()
                    _store_runtime_logs(run=run, browser=browser)
                    run.save(
                        update_fields=["status", "failure_reason", "final_summary", "finished_at", "updated_at"]
                    )
                    return run

                decision = agent.next_decision(
                    run_name=run.name,
                    target_url=target_url,
                    flow_description=(flow.description if flow else "") or "",
                    success_criteria=(flow.success_criteria if flow else "") or "",
                    login_hint=login_hint,
                    step_index=step_index,
                    max_steps=max_steps,
                    observation=observation,
                    history=history,
                )
                result = browser.execute_tool(decision.tool_name, decision.tool_input)
                _append_step(run=run, step_index=step_index, decision=decision, result=result)
                last_result = result

                history.append(
                    {
                        "step": step_index,
                        "tool": decision.tool_name,
                        "ok": result.ok,
                        "message": result.message,
                        "url": result.page_url,
                    }
                )

                if decision.tool_name == "observe_page":
                    observation = result.data if isinstance(result.data, dict) else {}
                    observation_signature = _build_observation_signature(observation, page_url=result.page_url)
                    repeat_action_key = ""
                    repeat_action_count = 0
                elif decision.tool_name == "take_screenshot":
                    observation = {**observation, "screenshot_taken": True, "url": result.page_url}
                elif decision.tool_name.startswith("finish_"):
                    if decision.tool_name == "finish_success" and result.ok:
                        run.status = TestRun.STATUS_SUCCESS
                        run.final_summary = result.message or "执行成功"
                        run.failure_reason = ""
                    else:
                        run.status = TestRun.STATUS_FAILED
                        run.final_summary = "执行失败"
                        run.failure_reason = result.message or "finish_failure"
                    break
                else:
                    observation = {
                        **observation,
                        "last_tool": decision.tool_name,
                        "last_message": result.message,
                        "url": result.page_url,
                    }

                if not result.ok:
                    shot = browser.execute_tool(
                        "take_screenshot",
                        {"reason": f"failure_step_{step_index}", "step_index": step_index},
                    )
                    failure_step = TestStepRun.objects.filter(run=run, step_index=step_index).first()
                    if failure_step and shot.screenshot:
                        _store_screenshot_artifact(
                            run=run,
                            step=failure_step,
                            file_name=shot.screenshot.file_name,
                            content=shot.screenshot.content,
                            mime_type=shot.screenshot.mime_type,
                        )
                    if decision.allow_failure:
                        observation = {
                            **observation,
                            "url": result.page_url,
                            "last_tool": decision.tool_name,
                            "last_message": result.message,
                            "optional_failure": True,
                        }
                        repeat_action_key = ""
                        repeat_action_count = 0
                        continue
                    run.status = TestRun.STATUS_FAILED
                    run.failure_reason = result.message or "tool_failed"
                    run.final_summary = f"第 {step_index} 步失败：{decision.tool_name}"
                    break

                guard_outcome = _handle_unsaved_confirmation_guard(
                    run=run,
                    browser=browser,
                    decision=decision,
                    step_index=step_index,
                )
                if guard_outcome is not None:
                    guarded_observation = guard_outcome.get("observation")
                    if isinstance(guarded_observation, dict):
                        observation = guarded_observation
                        observation_signature = _build_observation_signature(
                            observation,
                            page_url=(observation.get("url") or result.page_url or ""),
                        )
                    repeat_action_key = ""
                    repeat_action_count = 0

                # Seed actions often include login and may trigger delayed redirects.
                # Refresh observation once right after seed phase so the model does not reason on stale login-page state.
                if step_index == len(seed_actions):
                    try:
                        browser.page.wait_for_load_state("networkidle", timeout=min(5000, tool_timeout_secs * 1000))
                    except Exception:
                        pass
                    refresh = browser.execute_tool("observe_page", {"max_text": 1200, "max_elements": 40})
                    if refresh.ok and isinstance(refresh.data, dict):
                        observation = refresh.data
                        observation_signature = _build_observation_signature(observation, page_url=refresh.page_url)
                        repeat_action_key = ""
                        repeat_action_count = 0

                repeat_key = _build_repeat_action_key(
                    decision=decision,
                    observation_signature=observation_signature,
                    page_url=result.page_url,
                )
                if repeat_key:
                    if repeat_key == repeat_action_key:
                        repeat_action_count += 1
                    else:
                        repeat_action_key = repeat_key
                        repeat_action_count = 1
                else:
                    repeat_action_key = ""
                    repeat_action_count = 0

                if repeat_action_count >= LOOP_GUARD_THRESHOLD:
                    repeat_target = _extract_action_target(decision) or "-"
                    guard_reason = (
                        f"检测到重复动作循环：{decision.tool_name}({repeat_target}) "
                        f"连续 {repeat_action_count} 次且页面观测未变化"
                    )
                    screenshot_decision = AgentDecision(
                        "take_screenshot",
                        {"reason": "repeat_action_guard", "step_index": step_index + 1},
                        "循环保护：自动截图",
                    )
                    screenshot_result = browser.execute_tool(
                        screenshot_decision.tool_name,
                        screenshot_decision.tool_input,
                    )
                    _append_step(
                        run=run,
                        step_index=step_index + 1,
                        decision=screenshot_decision,
                        result=screenshot_result,
                    )

                    observe_decision = AgentDecision(
                        "observe_page",
                        {
                            "max_text": LOOP_GUARD_OBSERVE_MAX_TEXT,
                            "max_elements": LOOP_GUARD_OBSERVE_MAX_ELEMENTS,
                        },
                        "循环保护：自动观察页面",
                    )
                    observe_result = browser.execute_tool(observe_decision.tool_name, observe_decision.tool_input)
                    _append_step(
                        run=run,
                        step_index=step_index + 2,
                        decision=observe_decision,
                        result=observe_result,
                    )
                    if observe_result.ok and isinstance(observe_result.data, dict):
                        observation = observe_result.data
                        observation_signature = _build_observation_signature(
                            observation,
                            page_url=observe_result.page_url,
                        )

                    run.status = TestRun.STATUS_FAILED
                    run.failure_reason = guard_reason
                    run.final_summary = "执行失败（重复动作循环保护触发）"
                    break

            if run.status == TestRun.STATUS_RUNNING:
                if last_result and last_result.ok:
                    run.status = TestRun.STATUS_SUCCESS
                    run.final_summary = last_result.message or "执行完成"
                    run.failure_reason = ""
                else:
                    run.status = TestRun.STATUS_FAILED
                    run.failure_reason = (last_result.message if last_result else "") or "未达到成功条件"
                    run.final_summary = "执行结束但未满足成功条件"

            _store_runtime_logs(run=run, browser=browser)
            _run_expert_pipeline(
                run=run,
                flow=flow,
                llm_config=llm_config,
                reviewer_model=reviewer_model,
                timeout_secs=tool_timeout_secs,
                model_settings=model_settings,
            )

    except BrowserRuntimeUnavailable as exc:
        run.status = TestRun.STATUS_FAILED
        run.failure_reason = str(exc)
        run.final_summary = "浏览器运行时不可用，执行失败"
        if not TestStepRun.objects.filter(run=run).exists():
            _append_runtime_failure_step(run, str(exc))
    except Exception as exc:  # pragma: no cover - runtime safeguard
        logger.exception("ai-testing run failed: run=%s", run.id)
        run.status = TestRun.STATUS_FAILED
        run.failure_reason = str(exc)
        run.final_summary = "执行异常终止"
        if not TestStepRun.objects.filter(run=run).exists():
            _append_runtime_failure_step(run, str(exc))
    finally:
        run.finished_at = timezone.now()
        run.save(
            update_fields=[
                "status",
                "final_summary",
                "failure_reason",
                "finished_at",
                "updated_at",
            ]
        )
    return run


# Backward-compatible alias: old callers still reference execute_minimal_run.
execute_minimal_run = execute_ai_test_run
