from __future__ import annotations

import json

SYSTEM_PROMPT = (
    "你是软件测试专家代理。"
    "你只能输出 JSON，不允许输出 markdown 或解释性文本。"
    "你必须在受控工具集合中选择一个工具执行下一步。"
    "你具备长期软件测试技能：需求拆解、bug复现、探索式测试、失败归因。"
    "请基于普通用户给出的测试需求或bug现象，自主分解步骤并迭代尝试，不要求用户写完整脚本。"
    "执行 click 时，target 必须指向可交互控件（button/link/input 或 role=button），不要点击纯文本节点。"
    "必须采用 Observe->Act->Observe 的循环：关键动作后先观察页面，再决定下一步。"
    "如果出现二次确认框（例如 未保存/放弃编辑/离开页面/discard/unsaved changes），默认优先保留内容：点击“继续编辑/取消/留在此页”等按钮。"
    "除非任务明确要求放弃内容，否则不要点击“放弃/离开/discard”这类按钮。"
    "当界面出现弹窗叠弹窗时，要优先处理最上层确认框，并再次 observe_page 确认主弹窗仍在。"
    "当观察信息不足时，优先调用 observe_page(max_text>=1600,max_elements>=80) 获取更完整上下文。"
    "每一轮严格输出对象: "
    '{"thought":"简短思路","tool":"工具名","input":{"参数":"值"}}。'
    "当满足成功标准时使用 finish_success；当无法继续时使用 finish_failure。"
)

REVIEWER_SYSTEM_PROMPT = (
    "你是资深软件测试评审专家。"
    "请审查执行轨迹是否真正完成了测试需求或复现了bug。"
    "只输出 JSON，不要输出 markdown。"
    '输出格式: {"verdict":"pass|fail","reason":"简短结论","confidence":0~1,'
    '"should_create_issue":true|false,"priority":"P0|P1|P2|P3"}。'
)

ISSUE_WRITER_SYSTEM_PROMPT = (
    "你是缺陷报告专家。"
    "请根据测试执行证据生成可直接提交的缺陷标题和描述。"
    "只输出 JSON，不要输出 markdown。"
    '输出格式: {"title":"缺陷标题","description":"缺陷描述(含复现步骤/预期/实际/证据)","priority":"P0|P1|P2|P3"}。'
)


def build_agent_user_prompt(
    *,
    run_name: str,
    target_url: str,
    flow_description: str,
    success_criteria: str,
    login_hint: str,
    step_index: int,
    max_steps: int,
    observation: dict,
    history: list[dict],
) -> str:
    return (
        "任务上下文:\n"
        f"- run_name: {run_name}\n"
        f"- target_url: {target_url}\n"
        f"- flow_description: {flow_description or '-'}\n"
        f"- success_criteria: {success_criteria or '-'}\n"
        f"- login_hint: {login_hint or '-'}\n"
        f"- step: {step_index}/{max_steps}\n\n"
        "当前页面观察:\n"
        f"{json.dumps(observation, ensure_ascii=False)}\n\n"
        "最近执行历史(最多 6 条):\n"
        f"{json.dumps(history[-6:], ensure_ascii=False)}\n\n"
        "可用工具:\n"
        "- open_url {url}\n"
        "- observe_page {max_text,max_elements}\n"
        "- click {target}\n"
        "- fill {target,value}\n"
        "- press {key}\n"
        "- wait_for_text {text,timeout_ms}\n"
        "- assert_text {text,timeout_ms}\n"
        "- take_screenshot {reason}\n"
        "- finish_success {summary}\n"
        "- finish_failure {reason}\n\n"
        "执行约束:\n"
        "- 关闭弹窗/取消/ESC 后必须先 observe_page，再决定是否继续点击。\n"
        "- 若观察到“未保存/放弃编辑/离开页面/discard/unsaved”确认框，默认选择“继续编辑/取消/留在此页”。\n"
        "- 不要在未观察页面状态变化前连续重复点击同一目标。\n\n"
        "现在只输出 JSON。"
    )


def build_reviewer_user_prompt(
    *,
    run_name: str,
    flow_description: str,
    success_criteria: str,
    final_status: str,
    final_summary: str,
    failure_reason: str,
    steps: list[dict],
    artifacts: list[dict],
) -> str:
    return (
        "请评审以下测试执行结果是否有效:\n"
        f"- run_name: {run_name}\n"
        f"- flow_description: {flow_description or '-'}\n"
        f"- success_criteria: {success_criteria or '-'}\n"
        f"- final_status: {final_status}\n"
        f"- final_summary: {final_summary or '-'}\n"
        f"- failure_reason: {failure_reason or '-'}\n\n"
        "步骤(精简):\n"
        f"{json.dumps(steps, ensure_ascii=False)}\n\n"
        "证据(精简):\n"
        f"{json.dumps(artifacts, ensure_ascii=False)}\n\n"
        "请输出 verdict/reason/confidence/should_create_issue/priority 的 JSON。"
    )


def build_issue_writer_user_prompt(
    *,
    run_name: str,
    target_url: str,
    flow_description: str,
    reviewer_reason: str,
    steps: list[dict],
    artifacts: list[dict],
) -> str:
    return (
        "请基于以下测试执行证据生成缺陷单:\n"
        f"- run_name: {run_name}\n"
        f"- target_url: {target_url or '-'}\n"
        f"- flow_description: {flow_description or '-'}\n"
        f"- reviewer_reason: {reviewer_reason or '-'}\n\n"
        "步骤(精简):\n"
        f"{json.dumps(steps, ensure_ascii=False)}\n\n"
        "证据(精简):\n"
        f"{json.dumps(artifacts, ensure_ascii=False)}\n\n"
        "请输出 title/description/priority 的 JSON。"
    )
