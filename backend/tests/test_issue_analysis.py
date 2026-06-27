import json
import pytest
from unittest.mock import patch
from apps.ai.services import IssueAnalysisService
from apps.ai.models import Analysis
from tests.factories import (
    IssueFactory, RepoFactory, PromptFactory, LLMConfigFactory, AnalysisFactory,
    UserFactory,
)


@pytest.mark.django_db
class TestIssueAnalysesEndpoint:
    def test_list_analyses_returns_done(self, auth_client):
        issue = IssueFactory()
        user = UserFactory(name="CK")
        AnalysisFactory(
            analysis_type="issue_code_analysis",
            issue=issue,
            status="done",
            triggered_by="manual",
            triggered_by_user=user,
            parsed_result={"target_field": "cause", "content": "根因在 models.py"},
        )
        resp = auth_client.get(f"/api/issues/{issue.pk}/analyses/")
        assert resp.status_code == 200
        assert len(resp.data) == 1
        item = resp.data[0]
        assert item["status"] == "done"
        assert item["results"] == {"cause": "根因在 models.py"}
        assert item["triggered_by_user"] == "CK"
        assert item["error_message"] is None

    def test_list_analyses_failed_has_error(self, auth_client):
        issue = IssueFactory()
        AnalysisFactory(
            analysis_type="issue_code_analysis",
            issue=issue,
            status="failed",
            error_message="分析超时",
        )
        resp = auth_client.get(f"/api/issues/{issue.pk}/analyses/")
        assert resp.status_code == 200
        assert resp.data[0]["results"] is None
        assert resp.data[0]["error_message"] == "分析超时"

    def test_list_analyses_running_has_no_results(self, auth_client):
        issue = IssueFactory()
        AnalysisFactory(
            analysis_type="issue_code_analysis",
            issue=issue,
            status="running",
        )
        resp = auth_client.get(f"/api/issues/{issue.pk}/analyses/")
        assert resp.status_code == 200
        assert resp.data[0]["results"] is None
        assert resp.data[0]["error_message"] is None

    def test_list_analyses_excludes_other_types(self, auth_client):
        issue = IssueFactory()
        AnalysisFactory(analysis_type="team_insights", issue=issue, status="done")
        AnalysisFactory(analysis_type="issue_code_analysis", issue=issue, status="done",
                        parsed_result={"target_field": "cause", "content": "test"})
        resp = auth_client.get(f"/api/issues/{issue.pk}/analyses/")
        assert len(resp.data) == 1

    def test_list_analyses_ordered_newest_first(self, auth_client):
        issue = IssueFactory()
        a1 = AnalysisFactory(analysis_type="issue_code_analysis", issue=issue, status="done",
                             parsed_result={"target_field": "cause", "content": "old"})
        a2 = AnalysisFactory(analysis_type="issue_code_analysis", issue=issue, status="done",
                             parsed_result={"target_field": "cause", "content": "new"})
        resp = auth_client.get(f"/api/issues/{issue.pk}/analyses/")
        assert resp.data[0]["id"] == a2.id
        assert resp.data[1]["id"] == a1.id

    def test_list_analyses_requires_auth(self, api_client):
        issue = IssueFactory()
        resp = api_client.get(f"/api/issues/{issue.pk}/analyses/")
        assert resp.status_code == 401


@pytest.mark.django_db
class TestIssueAnalysisService:
    @pytest.fixture(autouse=True)
    def setup(self, db, settings):
        settings.REPO_CLONE_DIR = "/tmp/test_repos"
        self.config = LLMConfigFactory(is_default=True)
        self.prompt = PromptFactory(
            slug="issue_code_analysis",
            system_prompt="你是代码分析专家",
            user_prompt_template="分析问题: {title}\n描述: {description}",
        )
        self.repo = RepoFactory(clone_status="cloned", full_name="org/test-repo")
        self.issue = IssueFactory(repo=self.repo)
        self.svc = IssueAnalysisService()

    @patch("apps.ai.services.OpenCodeRunner")
    def test_analyze_stores_result_in_parsed_result(self, MockRunner):
        mock_instance = MockRunner.return_value
        inner = json.dumps({"target_field": "cause", "content": "根因是空指针"})
        mock_instance.run.return_value = json.dumps({
            "type": "text",
            "part": {"text": inner},
        })

        analysis = self.svc.analyze(self.issue, triggered_by="manual")
        assert analysis.status == "done"
        assert analysis.parsed_result["cause"] == "根因是空指针"
        self.issue.refresh_from_db()
        assert "根因是空指针" not in (self.issue.cause or "")

    @patch("apps.ai.services.OpenCodeRunner")
    def test_analyze_invalid_field_falls_back_to_remark(self, MockRunner):
        mock_instance = MockRunner.return_value
        inner = json.dumps({"target_field": "status", "content": "恶意内容"})
        mock_instance.run.return_value = json.dumps({
            "type": "text",
            "part": {"text": inner},
        })

        analysis = self.svc.analyze(self.issue, triggered_by="manual")
        assert analysis.status == "done"
        pr = analysis.parsed_result
        assert "cause" in pr or "solution" in pr or "remark" in pr

    def test_analyze_requires_cloned_repo(self):
        self.repo.clone_status = "not_cloned"
        self.repo.save()
        with pytest.raises(ValueError, match="请先同步代码"):
            self.svc.analyze(self.issue, triggered_by="manual")

    def test_analyze_requires_repo(self):
        self.issue.repo = None
        self.issue.save()
        with pytest.raises(ValueError, match="请先关联仓库"):
            self.svc.analyze(self.issue, triggered_by="manual")

    def test_no_duplicate_running_analysis(self):
        AnalysisFactory(
            issue=self.issue,
            analysis_type="issue_code_analysis",
            status="running",
        )
        existing = self.svc.get_running_analysis(self.issue)
        assert existing is not None

    def test_cleanup_stale_analyses(self):
        from django.utils import timezone
        from datetime import timedelta
        stale = AnalysisFactory(
            status="running",
            analysis_type="issue_code_analysis",
        )
        Analysis.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(minutes=15)
        )
        IssueAnalysisService.cleanup_stale_analyses()
        stale.refresh_from_db()
        assert stale.status == "failed"
        assert "进程异常终止" in stale.error_message

    @patch("apps.ai.services.OpenCodeRunner")
    def test_analysis_does_not_modify_issue_fields(self, MockRunner):
        issue = IssueFactory(repo=self.repo, cause="用户写的原因", solution="", remark="")
        mock_instance = MockRunner.return_value
        inner = json.dumps({"target_field": "cause", "content": "AI分析结果"})
        mock_instance.run.return_value = json.dumps({
            "type": "text",
            "part": {"text": inner},
        })

        analysis = self.svc.analyze(issue, triggered_by="manual")

        issue.refresh_from_db()
        assert issue.cause == "用户写的原因"  # unchanged
        assert analysis.status == "done"
        assert analysis.parsed_result["cause"] == "AI分析结果"


@pytest.mark.django_db
class TestIssueAIAnalyzeView:
    def test_trigger_returns_202(self, auth_client):
        repo = RepoFactory(full_name="org/test-repo", clone_status="cloned")
        issue = IssueFactory(repo=repo)
        with patch("apps.issues.views.IssueAnalysisService") as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.get_running_analysis.return_value = None
            mock_svc.analyze_async.return_value = AnalysisFactory(
                issue=issue, status="running"
            )
            resp = auth_client.post(f"/api/issues/{issue.pk}/ai-analyze/")
            assert resp.status_code == 202
            assert "analysis_id" in resp.data

    def test_no_repo_returns_400(self, auth_client):
        issue = IssueFactory(repo=None)
        resp = auth_client.post(f"/api/issues/{issue.pk}/ai-analyze/")
        assert resp.status_code == 400
        assert "关联仓库" in resp.data["detail"]

    def test_not_cloned_returns_400(self, auth_client):
        repo = RepoFactory(full_name="org/test-repo", clone_status="not_cloned")
        issue = IssueFactory(repo=repo)
        resp = auth_client.post(f"/api/issues/{issue.pk}/ai-analyze/")
        assert resp.status_code == 400
        assert "同步代码" in resp.data["detail"]

    def test_already_running_returns_409(self, auth_client):
        repo = RepoFactory(full_name="org/test-repo", clone_status="cloned")
        issue = IssueFactory(repo=repo)
        with patch("apps.issues.views.IssueAnalysisService") as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.get_running_analysis.return_value = AnalysisFactory(
                issue=issue, status="running"
            )
            resp = auth_client.post(f"/api/issues/{issue.pk}/ai-analyze/")
            assert resp.status_code == 409

    def test_not_found_returns_404(self, auth_client):
        resp = auth_client.post("/api/issues/99999/ai-analyze/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestAnalysisStatusView:
    def test_returns_status(self, auth_client):
        analysis = AnalysisFactory(status="done")
        resp = auth_client.get(f"/api/ai/analysis/{analysis.pk}/status/")
        assert resp.status_code == 200
        assert resp.data["status"] == "done"

    def test_not_found(self, auth_client):
        resp = auth_client.get("/api/ai/analysis/99999/status/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestAIStatusBatchView:
    """GET /api/issues/ai-status/?ids=1,2,3 — 批量查询 AI 分析运行状态,
    取代列表页逐条请求 /issues/{id}/ai-status/ 的 N+1。"""

    def test_requires_auth(self, api_client):
        resp = api_client.get("/api/issues/ai-status/?ids=1")
        assert resp.status_code in (401, 403)

    def test_returns_only_running_issue_ids(self, auth_client):
        running = IssueFactory()
        idle = IssueFactory()
        AnalysisFactory(
            issue=running, analysis_type="issue_code_analysis", status="running",
        )
        AnalysisFactory(
            issue=idle, analysis_type="issue_code_analysis", status="done",
        )
        resp = auth_client.get(f"/api/issues/ai-status/?ids={running.id},{idle.id}")
        assert resp.status_code == 200
        assert resp.data["running_ids"] == [running.id]

    def test_empty_ids_returns_empty(self, auth_client):
        resp = auth_client.get("/api/issues/ai-status/")
        assert resp.status_code == 200
        assert resp.data["running_ids"] == []

    def test_ignores_ids_outside_requested_set(self, auth_client):
        running = IssueFactory()
        AnalysisFactory(
            issue=running, analysis_type="issue_code_analysis", status="running",
        )
        # 只问别的 id,不应返回 running 的 id
        resp = auth_client.get(f"/api/issues/ai-status/?ids={running.id + 999}")
        assert resp.status_code == 200
        assert resp.data["running_ids"] == []

    def test_stale_running_times_out_and_excluded(self, auth_client):
        from django.utils import timezone
        from datetime import timedelta
        issue = IssueFactory()
        stale = AnalysisFactory(
            issue=issue, analysis_type="issue_code_analysis", status="running",
        )
        Analysis.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(minutes=15)
        )
        resp = auth_client.get(f"/api/issues/ai-status/?ids={issue.id}")
        assert resp.status_code == 200
        assert resp.data["running_ids"] == []
        stale.refresh_from_db()
        assert stale.status == "failed"

    def test_ignores_non_numeric_ids(self, auth_client):
        resp = auth_client.get("/api/issues/ai-status/?ids=abc,,7")
        assert resp.status_code == 200
        assert resp.data["running_ids"] == []
