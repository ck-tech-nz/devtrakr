"""Tests for auto_assign_issue (Phase 2 LLM-based implementation)."""
import json
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group

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


@pytest.fixture
def developer_role(db):
    # auto_assign_issue 仅在 role.name == "开发者" 的项目成员里挑人,
    # 所以测试 fixture 必须显式给成员挂上这个角色
    group, _ = Group.objects.get_or_create(name="开发者")
    return group


@pytest.mark.django_db
class TestAutoAssign:
    def _project_with_members(self, n=2, *, role=None):
        project = ProjectFactory()
        members = []
        for i in range(n):
            u = UserFactory(name=f"成员{i}")
            ProjectMember.objects.create(
                project=project,
                user=u,
                role=role,
                personal_description=f"负责模块 {i}",
            )
            members.append(u)
        return project, members

    def test_returns_event_on_valid_llm_response(self, auto_assign_prompt, default_llm_config, developer_role):
        project, members = self._project_with_members(2, role=developer_role)
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

    def test_returns_none_when_no_members_with_description(self, auto_assign_prompt, default_llm_config, developer_role):
        project = ProjectFactory()
        ProjectMember.objects.create(
            project=project,
            user=UserFactory(),
            role=developer_role,
            personal_description="",
        )
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        assert auto_assign_issue(issue) is None

    def test_returns_none_when_no_developer_members(self, auto_assign_prompt, default_llm_config):
        # 仅有非开发者角色的成员 (产品经理 / 测试 / 只读成员) 时,不应自动分派
        pm_role, _ = Group.objects.get_or_create(name="产品经理")
        project = ProjectFactory()
        ProjectMember.objects.create(
            project=project,
            user=UserFactory(),
            role=pm_role,
            personal_description="产品经理,负责需求",
        )
        ProjectMember.objects.create(
            project=project,
            user=UserFactory(),
            role=None,
            personal_description="未设角色,但写了描述",
        )
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        assert auto_assign_issue(issue) is None

    def test_skips_non_developer_members(self, auto_assign_prompt, default_llm_config, developer_role):
        # 同一项目中既有开发者又有产品经理时,只有开发者会出现在 LLM 候选里
        pm_role, _ = Group.objects.get_or_create(name="产品经理")
        project = ProjectFactory()
        dev = UserFactory(name="开发A")
        pm = UserFactory(name="产品B")
        ProjectMember.objects.create(
            project=project, user=dev, role=developer_role,
            personal_description="后端开发",
        )
        ProjectMember.objects.create(
            project=project, user=pm, role=pm_role,
            personal_description="产品经理",
        )
        issue = IssueFactory(project=project, status="待分配", assignee=None)

        # LLM 即便返回产品经理的 id,也应被候选校验拦下
        fake_response = json.dumps({"assignee_id": pm.id, "reason": "x"})
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = fake_response
            assert auto_assign_issue(issue) is None

    def test_returns_none_when_no_prompt(self, default_llm_config, developer_role):
        project, _ = self._project_with_members(2, role=developer_role)
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        # No active prompt with the right slug
        Prompt.objects.filter(slug="issue_auto_assign").update(is_active=False)
        assert auto_assign_issue(issue) is None

    def test_returns_none_on_llm_exception(self, auto_assign_prompt, default_llm_config, developer_role):
        project, _ = self._project_with_members(2, role=developer_role)
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.side_effect = RuntimeError("timeout")
            assert auto_assign_issue(issue) is None

    def test_returns_none_when_response_is_invalid_json(self, auto_assign_prompt, default_llm_config, developer_role):
        project, _ = self._project_with_members(2, role=developer_role)
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = "not json"
            assert auto_assign_issue(issue) is None

    def test_returns_none_when_assignee_id_not_in_project(self, auto_assign_prompt, default_llm_config, developer_role):
        project, members = self._project_with_members(2, role=developer_role)
        outsider = UserFactory()
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        fake_response = json.dumps({"assignee_id": outsider.id, "reason": "x"})
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = fake_response
            assert auto_assign_issue(issue) is None

    def test_workload_is_reflected_in_prompt(self, auto_assign_prompt, default_llm_config, developer_role):
        # members[0] 当前在本项目有 2 个活跃工单 (待确认+进行中);
        # members[1] 没有活跃工单。已关闭的工单不应计入。
        # 验证: LLM 收到的 user_prompt 中能正确读到两人的"活跃工单"数。
        project, members = self._project_with_members(2, role=developer_role)
        IssueFactory(project=project, status="进行中", assignee=members[0])
        IssueFactory(project=project, status="待确认", assignee=members[0])
        IssueFactory(project=project, status="已关闭", assignee=members[0])

        issue = IssueFactory(project=project, status="待分配", assignee=None)
        fake = json.dumps({"assignee_id": members[1].id, "reason": "更空闲"})
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = fake
            auto_assign_issue(issue)

        user_prompt = MockClient.return_value.complete.call_args.kwargs["user_prompt"]
        assert f"id={members[0].id}" in user_prompt
        assert f"id={members[1].id}" in user_prompt
        assert "活跃工单=2" in user_prompt
        assert "活跃工单=0" in user_prompt


@pytest.mark.django_db
class TestCreateIssueAutoAssignIntegration:
    def test_create_without_assignee_triggers_auto_assign(self, auto_assign_prompt, default_llm_config, developer_role):
        project = ProjectFactory()
        target = UserFactory()
        ProjectMember.objects.create(
            project=project,
            user=target,
            role=developer_role,
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
