from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.ai.client import LLMClient
from apps.ai.models import LLMConfig
from apps.ai.services import parse_json_response

from .browser import CONTROLLED_TOOLS
from .prompts import SYSTEM_PROMPT, build_agent_user_prompt


@dataclass
class AgentDecision:
    tool_name: str
    tool_input: dict[str, Any] = field(default_factory=dict)
    thought_summary: str = ""
    allow_failure: bool = False


class AITestAgent:
    def __init__(
        self,
        *,
        llm_config: LLMConfig | None,
        model: str,
        temperature: float,
        timeout_secs: int,
        seed_actions: list[AgentDecision] | None = None,
    ):
        self.llm_config = llm_config
        self.model = model
        self.temperature = temperature
        self.timeout_secs = timeout_secs
        self.seed_actions = seed_actions or []
        self._client = LLMClient(llm_config) if llm_config and model else None

    def next_decision(
        self,
        *,
        run_name: str,
        target_url: str,
        flow_description: str,
        success_criteria: str,
        login_hint: str,
        step_index: int,
        max_steps: int,
        observation: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> AgentDecision:
        if step_index <= len(self.seed_actions):
            return self.seed_actions[step_index - 1]

        forced_observe = self._build_forced_observe_decision(history=history)
        if forced_observe is not None:
            return forced_observe

        if self._client is None:
            return self._fallback_decision(
                step_index=step_index,
                max_steps=max_steps,
                target_url=target_url,
                success_criteria=success_criteria,
            )

        user_prompt = build_agent_user_prompt(
            run_name=run_name,
            target_url=target_url,
            flow_description=flow_description,
            success_criteria=success_criteria,
            login_hint=login_hint,
            step_index=step_index,
            max_steps=max_steps,
            observation=observation,
            history=history,
        )
        try:
            raw = self._client.complete(
                model=self.model,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=self.temperature,
                timeout=self.timeout_secs,
            )
            payload = parse_json_response(raw)
            return self._validate_payload(payload, step_index=step_index, max_steps=max_steps, target_url=target_url)
        except Exception as exc:
            return AgentDecision(
                "finish_failure",
                {"reason": f"planner_output_invalid: {exc}"},
                "模型规划输出格式异常，终止执行",
            )

    def _fallback_decision(
        self,
        *,
        step_index: int,
        max_steps: int,
        target_url: str,
        success_criteria: str,
    ) -> AgentDecision:
        if step_index == 1:
            return AgentDecision("open_url", {"url": target_url}, "打开目标页面")
        if step_index == 2:
            return AgentDecision("observe_page", {"max_text": 1200, "max_elements": 40}, "读取页面状态")
        if success_criteria and step_index == 3:
            return AgentDecision("assert_text", {"text": success_criteria, "timeout_ms": 15000}, "按成功标准断言")
        if step_index >= max_steps:
            return AgentDecision("finish_failure", {"reason": "达到最大步骤上限，自动停止"}, "防止无限执行")
        return AgentDecision("finish_success", {"summary": "fallback 执行完成"}, "最小策略收敛")

    def _validate_payload(
        self,
        payload: dict[str, Any],
        *,
        step_index: int,
        max_steps: int,
        target_url: str,
    ) -> AgentDecision:
        tool = str(payload.get("tool") or "").strip()
        if tool not in CONTROLLED_TOOLS:
            return self._fallback_decision(
                step_index=step_index,
                max_steps=max_steps,
                target_url=target_url,
                success_criteria="",
            )
        tool_input = payload.get("input")
        if not isinstance(tool_input, dict):
            tool_input = {}
        thought = str(payload.get("thought") or "").strip()[:280]
        return AgentDecision(tool_name=tool, tool_input=tool_input, thought_summary=thought)

    def _build_forced_observe_decision(self, *, history: list[dict[str, Any]]) -> AgentDecision | None:
        if not history:
            return None
        last_tool = str(history[-1].get("tool") or "").strip()
        if last_tool in {"observe_page", "take_screenshot", "finish_success", "finish_failure"}:
            return None
        if last_tool in {"click", "fill", "press", "open_url", "wait_for_text", "assert_text"}:
            return AgentDecision(
                "observe_page",
                {"max_text": 1800, "max_elements": 80},
                "动作后先观察页面，确认状态变化",
            )
        return None
