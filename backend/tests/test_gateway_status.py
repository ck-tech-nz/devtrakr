import pytest
import requests
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from apps.issues.views import _GW_CACHE_KEY

pytestmark = pytest.mark.django_db

URL = "/api/dashboard/gateway-status/"

UPSTREAM_OK = {
    "code": 0,
    "data": [
        {"id": 3, "name": "ippbx", "proxy_ip_list": "111.59.23.221", "port": 5060,
         "online": True, "ping_latency_ms": 13, "active_calls": 0,
         "today_calls": 6, "today_answered": 1, "today_answer_rate": 16.66,
         "ping_error": "", "last_ping_at": "2026-06-08T08:48:45Z"},
        {"id": 5, "name": "yd_test_in", "proxy_ip_list": "172.16.1.29", "port": 5060,
         "online": False, "ping_latency_ms": 3000, "active_calls": 0,
         "today_calls": 0, "today_answered": 0, "today_answer_rate": 0,
         "ping_error": "no response within timeout", "last_ping_at": "2026-06-08T08:48:48Z"},
    ],
}


def _ok_resp(payload):
    m = MagicMock()
    m.json.return_value = payload
    m.raise_for_status.return_value = None
    return m


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _configure(settings):
    settings.GATEWAY_STATUS_URL = "http://upstream.test/api/external/gateway-status"
    settings.GATEWAY_STATUS_API_KEY = "testkey"
    settings.GATEWAY_STATUS_CACHE_TTL = 12


def test_requires_auth(api_client):
    resp = api_client.get(URL)
    assert resp.status_code in (401, 403)


def test_unconfigured_returns_configured_false(auth_client, settings):
    settings.GATEWAY_STATUS_URL = ""
    settings.GATEWAY_STATUS_API_KEY = ""
    resp = auth_client.get(URL)
    assert resp.status_code == 200
    assert resp.json() == {"configured": False, "lines": []}


def test_success_normalizes_and_sends_key(auth_client, settings):
    _configure(settings)
    with patch("apps.issues.views.requests.get", return_value=_ok_resp(UPSTREAM_OK)) as mock_get:
        resp = auth_client.get(URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["stale"] is False
    assert "fetched_at" in body
    assert [l["name"] for l in body["lines"]] == ["ippbx", "yd_test_in"]
    mock_get.assert_called_once_with(
        settings.GATEWAY_STATUS_URL,
        headers={"X-API-Key": "testkey"},
        timeout=8,
        allow_redirects=False,  # 不跟随重定向:挡掉明文上游被劫持后的 SSRF 跳转
    )


def test_non_list_upstream_data_yields_empty_lines(auth_client, settings):
    _configure(settings)
    bad = {"code": 0, "data": {"unexpected": "shape"}}  # code:0 但 data 非数组
    with patch("apps.issues.views.requests.get", return_value=_ok_resp(bad)):
        resp = auth_client.get(URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["stale"] is False
    assert body["lines"] == []  # 脏 data 规整为空,不透传给前端(避免前端 .filter 崩溃)


def test_second_request_served_from_cache(auth_client, settings):
    _configure(settings)
    with patch("apps.issues.views.requests.get", return_value=_ok_resp(UPSTREAM_OK)) as mock_get:
        auth_client.get(URL)
        resp2 = auth_client.get(URL)
    assert resp2.status_code == 200
    assert mock_get.call_count == 1  # 第二次命中 12s 短缓存


def test_stale_fallback_to_last_good(auth_client, settings):
    _configure(settings)
    # 第一次成功 → 写 last-good
    with patch("apps.issues.views.requests.get", return_value=_ok_resp(UPSTREAM_OK)):
        auth_client.get(URL)
    cache.delete(_GW_CACHE_KEY)  # 模拟 12s 短缓存过期,last-good 仍在
    # 第二次上游失败 → 回退 last-good
    with patch("apps.issues.views.requests.get", side_effect=requests.RequestException("boom")):
        resp = auth_client.get(URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stale"] is True
    assert [l["name"] for l in body["lines"]] == ["ippbx", "yd_test_in"]


def test_upstream_error_without_cache(auth_client, settings):
    _configure(settings)
    with patch("apps.issues.views.requests.get", side_effect=requests.RequestException("boom")):
        resp = auth_client.get(URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"configured": True, "stale": True, "lines": [], "error": "upstream_unavailable"}


def test_bad_upstream_code_falls_back(auth_client, settings):
    _configure(settings)
    bad = _ok_resp({"code": 1, "msg": "upstream error"})
    with patch("apps.issues.views.requests.get", return_value=bad):
        resp = auth_client.get(URL)
    assert resp.status_code == 200
    assert resp.json() == {"configured": True, "stale": True, "lines": [], "error": "upstream_unavailable"}
