import pytest
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_user_list_includes_is_superuser(superuser_client):
    UserFactory(is_superuser=False)
    resp = superuser_client.get("/api/users/")
    assert resp.status_code == 200
    rows = resp.json()["results"]
    assert rows, "expected at least one user in results"
    assert all("is_superuser" in row for row in rows)


def test_superuser_can_impersonate_regular_user(superuser_client):
    target = UserFactory(is_superuser=False, is_active=True)
    resp = superuser_client.post("/api/auth/impersonate/", {"user_id": target.id})
    assert resp.status_code == 200
    body = resp.json()
    assert "access" in body and "refresh" in body
    token = AccessToken(body["access"])
    # simplejwt 5.5+ 把 user_id claim 序列化为字符串（兼容 UUID 主键），故需转回 int 比较
    assert int(token["user_id"]) == target.id
    assert token["impersonated_by"] is not None


def test_can_impersonate_staff_non_superuser(superuser_client):
    target = UserFactory(is_superuser=False, is_staff=True, is_active=True)
    resp = superuser_client.post("/api/auth/impersonate/", {"user_id": target.id})
    assert resp.status_code == 200


def test_cannot_impersonate_superuser(superuser_client):
    target = UserFactory(is_superuser=True, is_active=True)
    resp = superuser_client.post("/api/auth/impersonate/", {"user_id": target.id})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "不能模拟管理员账号"


def test_cannot_impersonate_inactive_user(superuser_client):
    target = UserFactory(is_superuser=False, is_active=False)
    resp = superuser_client.post("/api/auth/impersonate/", {"user_id": target.id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "该用户未激活"


def test_target_not_found_returns_404(superuser_client):
    resp = superuser_client.post("/api/auth/impersonate/", {"user_id": 99999999})
    assert resp.status_code == 404


def test_regular_user_cannot_impersonate(regular_client):
    target = UserFactory(is_superuser=False, is_active=True)
    resp = regular_client.post("/api/auth/impersonate/", {"user_id": target.id})
    assert resp.status_code == 403


def test_nested_impersonation_rejected(superuser_client):
    target = UserFactory(is_superuser=False, is_active=True)
    other = UserFactory(is_superuser=False, is_active=True)
    resp = superuser_client.post("/api/auth/impersonate/", {"user_id": target.id})
    access = resp.json()["access"]
    # 用全新客户端，仅凭模拟态 access token 鉴权（避免 force_authenticate 把 request.auth 置空）
    from rest_framework.test import APIClient
    impersonated = APIClient()
    impersonated.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    resp2 = impersonated.post("/api/auth/impersonate/", {"user_id": other.id})
    assert resp2.status_code == 403
    # 必须由嵌套守卫返回，而非 is_superuser 校验（两者 detail 不同）
    assert resp2.json()["detail"] == "不可嵌套模拟"


def test_impersonation_refresh_token_is_short_lived(superuser_client):
    target = UserFactory(is_superuser=False, is_active=True)
    resp = superuser_client.post("/api/auth/impersonate/", {"user_id": target.id})
    refresh = RefreshToken(resp.json()["refresh"])
    assert refresh["exp"] - refresh["iat"] <= 3600


def test_me_reflects_impersonation(superuser_client, api_client, site_settings):
    target = UserFactory(is_superuser=False, is_active=True)
    resp = superuser_client.post("/api/auth/impersonate/", {"user_id": target.id})
    access = resp.json()["access"]
    # superuser_client 与 api_client 是同一个被 force_authenticate 的实例，
    # _force_user 会盖过 Bearer 头导致请求仍以超管身份解析；
    # 故用全新客户端，仅凭模拟态 access token 走真实 JWT 鉴权。
    from rest_framework.test import APIClient
    impersonated = APIClient()
    impersonated.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    me = impersonated.get("/api/auth/me/")
    assert me.status_code == 200
    body = me.json()
    assert int(body["id"]) == target.id
    assert body["impersonated_by"] is not None
    assert body["impersonated_by_username"]


def test_me_without_impersonation_is_null(superuser_client):
    me = superuser_client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["impersonated_by"] is None
    assert me.json()["impersonated_by_username"] is None
