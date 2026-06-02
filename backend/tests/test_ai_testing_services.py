import pytest

from apps.ai_testing.agent import AgentDecision
from apps.ai_testing.browser import BrowserRuntimeUnavailable, BrowserToolResult, ScreenshotPayload
from apps.ai_testing.models import ProjectEnvironment, TestRun as AITestRunModel
from apps.ai_testing.services import LOOP_GUARD_OBSERVE_MAX_ELEMENTS, execute_ai_test_run
from tests.factories import AITestFlowFactory, AITestRunFactory, ProjectEnvironmentFactory

pytestmark = pytest.mark.django_db


def test_execute_ai_run_fails_when_browser_runtime_unavailable(monkeypatch):
    run = AITestRunFactory(status=AITestRunModel.STATUS_PENDING)

    class BrokenBrowser:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            raise BrowserRuntimeUnavailable("playwright unavailable in runtime")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("apps.ai_testing.services.HeadlessBrowserSession", BrokenBrowser)

    execute_ai_test_run(run)
    run.refresh_from_db()
    assert run.status == AITestRunModel.STATUS_FAILED
    assert "playwright unavailable" in run.failure_reason
    assert run.finished_at is not None
    assert run.steps.count() == 1
    assert run.steps.first().tool_name == "runtime_error"


def test_execute_ai_run_success_with_fake_browser(monkeypatch):
    env = ProjectEnvironmentFactory(
        login_type=ProjectEnvironment.LOGIN_NONE,
        login_username="",
    )
    flow = AITestFlowFactory(project=env.project, environment=env, success_criteria="")
    run = AITestRunFactory(
        status=AITestRunModel.STATUS_PENDING,
        flow=flow,
        project=flow.project,
        environment=flow.environment,
    )

    class FakeBrowser:
        def __init__(self, *args, **kwargs):
            self.console_logs = []
            self.network_errors = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute_tool(self, tool_name, tool_input):
            if tool_name == "open_url":
                return BrowserToolResult(
                    ok=True,
                    message="opened",
                    data={"status_code": 200},
                    page_url="https://example.com",
                )
            if tool_name == "observe_page":
                return BrowserToolResult(
                    ok=True,
                    message="observed",
                    data={"title": "Demo", "visible_text": "ok"},
                    page_url="https://example.com",
                )
            if tool_name == "finish_success":
                return BrowserToolResult(
                    ok=True,
                    message="done",
                    data={"finished": "success"},
                    page_url="https://example.com",
                )
            return BrowserToolResult(
                ok=True,
                message=f"{tool_name}:ok",
                data={},
                page_url="https://example.com",
            )

    monkeypatch.setattr("apps.ai_testing.services.HeadlessBrowserSession", FakeBrowser)
    execute_ai_test_run(run)
    run.refresh_from_db()
    assert run.status == AITestRunModel.STATUS_SUCCESS
    assert run.steps.count() >= 2


def test_execute_ai_run_does_not_abort_on_optional_login_seed_failures(monkeypatch):
    env = ProjectEnvironmentFactory(
        login_type=ProjectEnvironment.LOGIN_USERNAME_PASSWORD,
        login_username="tester",
        login_password="pass123456",
    )
    flow = AITestFlowFactory(project=env.project, environment=env, success_criteria="")
    run = AITestRunFactory(
        status=AITestRunModel.STATUS_PENDING,
        flow=flow,
        project=flow.project,
        environment=flow.environment,
    )

    class FakeBrowser:
        def __init__(self, *args, **kwargs):
            self.console_logs = []
            self.network_errors = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute_tool(self, tool_name, tool_input):
            if tool_name == "open_url":
                return BrowserToolResult(ok=True, message="opened", data={}, page_url="https://example.com")
            if tool_name in {"click", "fill"}:
                return BrowserToolResult(ok=False, message=f"{tool_name}: target not found", data={}, page_url="https://example.com")
            if tool_name == "take_screenshot":
                return BrowserToolResult(ok=True, message="shot", data={}, page_url="https://example.com")
            if tool_name == "finish_success":
                return BrowserToolResult(ok=True, message="done", data={}, page_url="https://example.com")
            return BrowserToolResult(ok=True, message=f"{tool_name}:ok", data={}, page_url="https://example.com")

    monkeypatch.setattr("apps.ai_testing.services.HeadlessBrowserSession", FakeBrowser)
    execute_ai_test_run(run)
    run.refresh_from_db()

    assert run.status == AITestRunModel.STATUS_SUCCESS
    assert run.steps.filter(status="failed").count() >= 1


def test_execute_ai_run_timeout_persists_timeout_step_and_runtime_artifacts(monkeypatch):
    env = ProjectEnvironmentFactory(
        login_type=ProjectEnvironment.LOGIN_NONE,
        login_username="",
    )
    flow = AITestFlowFactory(project=env.project, environment=env, success_criteria="", timeout_secs=0)
    run = AITestRunFactory(
        status=AITestRunModel.STATUS_PENDING,
        flow=flow,
        project=flow.project,
        environment=flow.environment,
    )

    class FakeBrowser:
        def __init__(self, *args, **kwargs):
            self.console_logs = [{"type": "log", "text": "hello-timeout"}]
            self.network_errors = [{"method": "GET", "url": "https://example.com/x", "failure": "net::ERR_FAILED"}]
            self.page = type("Page", (), {"url": "https://example.com"})()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute_tool(self, tool_name, tool_input):
            if tool_name == "take_screenshot":
                return BrowserToolResult(
                    ok=True,
                    message="shot",
                    page_url="https://example.com",
                    screenshot=ScreenshotPayload(
                        file_name="timeout.png",
                        content=b"png",
                        mime_type="image/png",
                    ),
                )
            return BrowserToolResult(
                ok=True,
                message=f"{tool_name}:ok",
                data={},
                page_url="https://example.com",
            )

    monkeypatch.setattr("apps.ai_testing.services.HeadlessBrowserSession", FakeBrowser)
    execute_ai_test_run(run)
    run.refresh_from_db()

    assert run.status == AITestRunModel.STATUS_TIMEOUT
    timeout_step = run.steps.order_by("-step_index").first()
    assert timeout_step is not None
    assert timeout_step.tool_name == "timeout_guard"
    artifact_types = sorted(run.artifacts.values_list("artifact_type", flat=True))
    assert "console_log" in artifact_types
    assert "network_log" in artifact_types


def test_execute_ai_run_aborts_on_repeated_actions_without_page_progress(monkeypatch):
    env = ProjectEnvironmentFactory(
        login_type=ProjectEnvironment.LOGIN_NONE,
        login_username="",
    )
    flow = AITestFlowFactory(project=env.project, environment=env, success_criteria="", max_steps=12)
    run = AITestRunFactory(
        status=AITestRunModel.STATUS_PENDING,
        flow=flow,
        project=flow.project,
        environment=flow.environment,
    )

    class FakePage:
        def __init__(self):
            self.url = "https://example.com/issues"

        def wait_for_load_state(self, *args, **kwargs):
            return None

    class FakeBrowser:
        def __init__(self, *args, **kwargs):
            self.console_logs = []
            self.network_errors = []
            self.page = FakePage()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute_tool(self, tool_name, tool_input):
            if tool_name == "open_url":
                self.page.url = tool_input.get("url") or self.page.url
                return BrowserToolResult(ok=True, message="opened", data={}, page_url=self.page.url)
            if tool_name == "observe_page":
                return BrowserToolResult(
                    ok=True,
                    message="observed",
                    data={
                        "title": "Issues",
                        "visible_text": "问题列表 新建问题",
                        "interactive_elements": [
                            {"tag": "span", "role": "", "text": "新建问题"},
                        ],
                    },
                    page_url=self.page.url,
                )
            if tool_name == "click":
                return BrowserToolResult(ok=True, message="clicked", data={}, page_url=self.page.url)
            if tool_name == "take_screenshot":
                return BrowserToolResult(ok=True, message="shot", data={}, page_url=self.page.url)
            return BrowserToolResult(ok=True, message=f"{tool_name}:ok", data={}, page_url=self.page.url)

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def next_decision(self, **kwargs):
            step_index = kwargs["step_index"]
            if step_index == 1:
                return AgentDecision(
                    "open_url",
                    {"url": "https://example.com/issues"},
                    "open",
                )
            if step_index == 2:
                return AgentDecision(
                    "observe_page",
                    {"max_text": 1200, "max_elements": 40},
                    "observe",
                )
            return AgentDecision(
                "click",
                {"target": "text=新建问题"},
                "click",
            )

    monkeypatch.setattr("apps.ai_testing.services.HeadlessBrowserSession", FakeBrowser)
    monkeypatch.setattr("apps.ai_testing.services.AITestAgent", FakeAgent)

    execute_ai_test_run(run)
    run.refresh_from_db()

    assert run.status == AITestRunModel.STATUS_FAILED
    assert "重复动作循环" in run.failure_reason
    guard_observe_step = run.steps.filter(thought_summary="循环保护：自动观察页面").first()
    assert guard_observe_step is not None
    assert guard_observe_step.tool_input["max_elements"] == LOOP_GUARD_OBSERVE_MAX_ELEMENTS
    assert run.steps.filter(thought_summary="循环保护：自动截图", tool_name="take_screenshot").exists()


def test_execute_ai_run_recovers_from_unsaved_changes_confirmation(monkeypatch):
    env = ProjectEnvironmentFactory(
        login_type=ProjectEnvironment.LOGIN_NONE,
        login_username="",
    )
    flow = AITestFlowFactory(project=env.project, environment=env, success_criteria="", max_steps=10)
    run = AITestRunFactory(
        status=AITestRunModel.STATUS_PENDING,
        flow=flow,
        project=flow.project,
        environment=flow.environment,
    )

    class FakePage:
        def __init__(self):
            self.url = "https://example.com/issues"

        def wait_for_load_state(self, *args, **kwargs):
            return None

    class FakeBrowser:
        def __init__(self, *args, **kwargs):
            self.console_logs = []
            self.network_errors = []
            self.page = FakePage()
            self.confirm_open = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute_tool(self, tool_name, tool_input):
            if tool_name == "open_url":
                return BrowserToolResult(ok=True, message="opened", data={}, page_url=self.page.url)
            if tool_name == "observe_page":
                if self.confirm_open:
                    return BrowserToolResult(
                        ok=True,
                        message="observed-confirm",
                        data={
                            "title": "确认弹窗",
                            "visible_text": "放弃编辑？关闭后将丢失。确定要放弃吗？",
                            "interactive_elements": [],
                            "unsaved_changes_dialog": {
                                "detected": True,
                                "dialog_text": "放弃编辑？",
                                "recover_target": "继续编辑",
                                "discard_target": "放弃",
                            },
                        },
                        page_url=self.page.url,
                    )
                return BrowserToolResult(
                    ok=True,
                    message="observed",
                    data={
                        "title": "新建问题",
                        "visible_text": "新建问题 表单",
                        "interactive_elements": [],
                        "unsaved_changes_dialog": {
                            "detected": False,
                            "dialog_text": "",
                            "recover_target": "",
                            "discard_target": "",
                        },
                    },
                    page_url=self.page.url,
                )
            if tool_name == "click":
                target = str(tool_input.get("target") or "")
                if "关闭" in target:
                    self.confirm_open = True
                if "继续编辑" in target:
                    self.confirm_open = False
                return BrowserToolResult(ok=True, message=f"clicked:{target}", data={}, page_url=self.page.url)
            if tool_name == "finish_success":
                return BrowserToolResult(ok=True, message="done", data={}, page_url=self.page.url)
            return BrowserToolResult(ok=True, message=f"{tool_name}:ok", data={}, page_url=self.page.url)

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def next_decision(self, **kwargs):
            step_index = kwargs["step_index"]
            if step_index == 1:
                return AgentDecision("open_url", {"url": "https://example.com/issues"}, "open")
            if step_index == 2:
                return AgentDecision("observe_page", {"max_text": 1200, "max_elements": 40}, "observe")
            if step_index == 3:
                return AgentDecision("click", {"target": "text=关闭"}, "close modal")
            return AgentDecision("finish_success", {"summary": "ok"}, "done")

    monkeypatch.setattr("apps.ai_testing.services.HeadlessBrowserSession", FakeBrowser)
    monkeypatch.setattr("apps.ai_testing.services.AITestAgent", FakeAgent)

    execute_ai_test_run(run)
    run.refresh_from_db()

    assert run.status == AITestRunModel.STATUS_SUCCESS
    assert run.steps.filter(thought_summary="弹窗保护：检查二次确认框", tool_name="observe_page").exists()
    recover_step = run.steps.filter(thought_summary="弹窗保护：优先继续编辑，避免内容丢失", tool_name="click").first()
    assert recover_step is not None
    assert recover_step.tool_input["target"] == "text=继续编辑"
