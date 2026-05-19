import pytest
from django.db import IntegrityError, transaction
from apps.projects.models import ProjectMember
from tests.factories import ProjectFactory, UserFactory, ProjectMemberFactory


@pytest.mark.django_db
class TestProjectManager:
    def test_default_is_manager_false(self):
        m = ProjectMemberFactory()
        assert m.is_manager is False

    def test_can_set_is_manager_true(self):
        project = ProjectFactory()
        u = UserFactory()
        m = ProjectMember.objects.create(project=project, user=u, is_manager=True)
        assert m.is_manager is True

    def test_only_one_manager_per_project(self):
        project = ProjectFactory()
        u1, u2 = UserFactory(), UserFactory()
        ProjectMember.objects.create(project=project, user=u1, is_manager=True)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ProjectMember.objects.create(project=project, user=u2, is_manager=True)

    def test_two_projects_can_each_have_a_manager(self):
        p1, p2 = ProjectFactory(), ProjectFactory()
        u1, u2 = UserFactory(), UserFactory()
        ProjectMember.objects.create(project=p1, user=u1, is_manager=True)
        ProjectMember.objects.create(project=p2, user=u2, is_manager=True)
        assert ProjectMember.objects.filter(is_manager=True).count() == 2


@pytest.mark.django_db
class TestProjectMemberAPI:
    def test_patch_member_to_be_manager(self, auth_client):
        project = ProjectFactory()
        user = UserFactory()
        member = ProjectMember.objects.create(project=project, user=user, is_manager=False)
        resp = auth_client.patch(
            f"/api/projects/{project.id}/members/{user.id}/",
            {"is_manager": True}, format="json",
        )
        assert resp.status_code == 200, resp.data
        member.refresh_from_db()
        assert member.is_manager is True

    def test_setting_second_manager_returns_409(self, auth_client):
        project = ProjectFactory()
        u1, u2 = UserFactory(), UserFactory()
        ProjectMember.objects.create(project=project, user=u1, is_manager=True)
        ProjectMember.objects.create(project=project, user=u2)
        resp = auth_client.patch(
            f"/api/projects/{project.id}/members/{u2.id}/",
            {"is_manager": True}, format="json",
        )
        assert resp.status_code == 409

    def test_creating_second_manager_via_post_returns_409(self, auth_client):
        project = ProjectFactory()
        u1, u2 = UserFactory(), UserFactory()
        ProjectMember.objects.create(project=project, user=u1, is_manager=True)
        resp = auth_client.post(
            f"/api/projects/{project.id}/members/",
            {"user_id": u2.id, "is_manager": True}, format="json",
        )
        assert resp.status_code == 409, resp.data


@pytest.mark.django_db
class TestManagerSnapshot:
    def test_issue_manager_snapshot_unchanged_when_project_manager_changes(self):
        """Issue.manager must be a snapshot — unaffected by subsequent project manager changes."""
        from apps.issues.services import create_issue

        project = ProjectFactory()
        mgr1 = UserFactory(name="经理一号")
        mgr2 = UserFactory(name="经理二号")
        member1 = ProjectMember.objects.create(project=project, user=mgr1, is_manager=True)

        issue = create_issue(
            project=project, actor=UserFactory(),
            title="t", description="d", priority="P2", assignee=None,
        )
        assert issue.manager == mgr1

        # Swap project manager: demote mgr1, promote mgr2
        member1.is_manager = False
        member1.save()
        ProjectMember.objects.create(project=project, user=mgr2, is_manager=True)

        issue.refresh_from_db()
        assert issue.manager == mgr1, "Issue.manager snapshot must NOT change when project's manager changes"
