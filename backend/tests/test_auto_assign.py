"""Tests for auto_assign_issue (Phase 2 LLM-based implementation)."""
import json
from unittest.mock import patch

import pytest

from apps.ai.models import Prompt
from apps.issues.models import AssignmentAction
from apps.issues.services import auto_assign_issue, create_issue
from apps.projects.models import ProjectMember

from tests.factories import (
    IssueFactory,
    LLMConfigFactory,
    ProjectFactory,
    PromptFactory,
    UserFactory,
)


@pytest.fixture
def auto_assign_prompt(db):
    # Replace any seeded prompt so we have full control over the template
    Prompt.objects.filter(slug="issue_auto_assign").delete()
    return PromptFactory(
        slug="issue_auto_assign",
        system_prompt="你是分配助手。只返回JSON。",
        user_prompt_template="{title} {description} {labels} {priority} {members_block}",
        is_active=True,
    )


@pytest.fixture
def default_llm_config(db):
    return LLMConfigFactory(is_default=True, is_active=True)


@pytest.mark.django_db
class TestAutoAssign:
    def _project_with_members(self, n=2):
        project = ProjectFactory()
        members = []
        for i in range(n):
            u = UserFactory(name=f"成员{i}")
            ProjectMember.objects.create(
                project=project,
                user=u,
                personal_description=f"负责模块 {i}",
            )
            members.append(u)
        return project, members

    def test_returns_event_on_valid_llm_response(self, auto_assign_prompt, default_llm_config):
        project, members = self._project_with_members(2)
        issue = IssueFactory(project=project, status="待分配", assignee=None)

        fake_response = json.dumps({"assignee_id": members[1].id, "reason": "更贴合"})
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = fake_response
            ev = auto_assign_issue(issue)

        assert ev is not None
        assert ev.action == AssignmentAction.AI_ASSIGN
        assert ev.to_user == members[1]
        assert ev.actor is None
        issue.refresh_from_db()
        assert issue.assignee == members[1]
        assert issue.status == "待确认"

    def test_returns_none_when_no_members_with_description(self, auto_assign_prompt, default_llm_config):
        project = ProjectFactory()
        ProjectMember.objects.create(
            project=project,
            user=UserFactory(),
            personal_description="",
        )
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        assert auto_assign_issue(issue) is None

    def test_returns_none_when_no_llm_config(self, auto_assign_prompt):
        project, _ = self._project_with_members(2)
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        # No active LLMConfig → should return None
        assert auto_assign_issue(issue) is None

    def test_returns_none_when_no_prompt(self, default_llm_config):
        project, _ = self._project_with_members(2)
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        # No active prompt with the right slug
        Prompt.objects.filter(slug="issue_auto_assign").update(is_active=False)
        assert auto_assign_issue(issue) is None

    def test_returns_none_on_llm_exception(self, auto_assign_prompt, default_llm_config):
        project, _ = self._project_with_members(2)
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.side_effect = RuntimeError("timeout")
            assert auto_assign_issue(issue) is None

    def test_returns_none_when_response_is_invalid_json(self, auto_assign_prompt, default_llm_config):
        project, _ = self._project_with_members(2)
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = "not json"
            assert auto_assign_issue(issue) is None

    def test_returns_none_when_assignee_id_not_in_project(self, auto_assign_prompt, default_llm_config):
        project, members = self._project_with_members(2)
        outsider = UserFactory()
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        fake_response = json.dumps({"assignee_id": outsider.id, "reason": "x"})
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = fake_response
            assert auto_assign_issue(issue) is None


@pytest.mark.django_db
class TestCreateIssueAutoAssignIntegration:
    def test_create_without_assignee_triggers_auto_assign(self, auto_assign_prompt, default_llm_config):
        project = ProjectFactory()
        target = UserFactory()
        ProjectMember.objects.create(
            project=project,
            user=target,
            personal_description="后端专家",
        )

        fake = json.dumps({"assignee_id": target.id, "reason": "后端"})
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = fake
            issue = create_issue(
                project=project,
                actor=UserFactory(),
                title="修复登录Bug",
                description="无法登录系统",
                priority="P1",
            )

        issue.refresh_from_db()
        assert issue.assignee == target
        assert issue.status == "待确认"
