from apps.ai_testing.agent import AITestAgent


class _DummyClient:
    def __init__(self, output: str):
        self.output = output

    def complete(self, **kwargs):
        return self.output


def test_agent_returns_finish_failure_on_invalid_planner_output():
    agent = AITestAgent(
        llm_config=None,
        model="dummy",
        temperature=0.1,
        timeout_secs=10,
    )
    agent._client = _DummyClient("not-json")

    decision = agent.next_decision(
        run_name="run",
        target_url="https://example.com",
        flow_description="",
        success_criteria="",
        login_hint="",
        step_index=4,
        max_steps=30,
        observation={},
        history=[],
    )

    assert decision.tool_name == "finish_failure"
    assert "planner_output_invalid" in decision.tool_input.get("reason", "")


def test_agent_forces_observe_after_action_history():
    agent = AITestAgent(
        llm_config=None,
        model="dummy",
        temperature=0.1,
        timeout_secs=10,
    )
    agent._client = _DummyClient('{"tool":"finish_success","input":{"summary":"done"},"thought":"done"}')

    decision = agent.next_decision(
        run_name="run",
        target_url="https://example.com",
        flow_description="",
        success_criteria="",
        login_hint="",
        step_index=5,
        max_steps=30,
        observation={},
        history=[{"step": 4, "tool": "click", "ok": True, "message": "clicked", "url": "https://example.com"}],
    )

    assert decision.tool_name == "observe_page"
    assert decision.tool_input["max_elements"] >= 80
