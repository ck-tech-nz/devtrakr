import pytest
from tests.factories import UserFactory, GroupFactory

pytestmark = pytest.mark.django_db


class TestUserChoices:
    def test_choices_returns_active_non_bot(self, auth_client):
        UserFactory(name="开发A")
        UserFactory(name="机器人", is_bot=True)
        response = auth_client.get("/api/users/choices/")
        assert response.status_code == 200
        names = {u["name"] for u in response.data}
        assert "开发A" in names
        assert "机器人" not in names

    def test_choices_filter_by_group(self, auth_client):
        # 负责人下拉按用户组筛选:?group=开发者 仅返回该组成员
        dev_group = GroupFactory(name="开发者")
        dev = UserFactory(name="开发A")
        dev.groups.add(dev_group)
        UserFactory(name="非开发B")  # 不在开发者组
        response = auth_client.get("/api/users/choices/?group=开发者")
        assert response.status_code == 200
        names = {u["name"] for u in response.data}
        assert names == {"开发A"}

    def test_choices_includes_groups_per_user(self, auth_client):
        # 每个用户带上所属组名,前端据此自行分组,免去额外的 ?group= 调用
        dev_group = GroupFactory(name="开发者")
        tester_group = GroupFactory(name="测试")
        dev = UserFactory(name="开发A")
        dev.groups.add(dev_group, tester_group)
        UserFactory(name="无组C")
        response = auth_client.get("/api/users/choices/")
        assert response.status_code == 200
        by_name = {u["name"]: u for u in response.data}
        assert set(by_name["开发A"]["groups"]) == {"开发者", "测试"}
        assert by_name["无组C"]["groups"] == []


class TestUserList:
    def test_list_users(self, auth_client):
        UserFactory.create_batch(3)
        response = auth_client.get("/api/users/")
        assert response.status_code == 200
        # auth_client creates 1 user + 3 = 4 total
        assert len(response.data) == 4

    def test_list_users_unauthenticated(self, api_client):
        response = api_client.get("/api/users/")
        assert response.status_code == 401


class TestUserDetail:
    def test_get_user_detail(self, auth_client):
        user = UserFactory(name="李四", github_id="lisi")
        response = auth_client.get(f"/api/users/{user.id}/")
        assert response.status_code == 200
        assert response.data["name"] == "李四"
        assert response.data["github_id"] == "lisi"
