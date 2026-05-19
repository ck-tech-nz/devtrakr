import pytest
from rest_framework.test import APIClient, APIRequestFactory
from tests.factories import ExternalAPIKeyFactory, IssueFactory


@pytest.mark.django_db
class TestExternalAPIKeyModel:
    def test_create_api_key(self):
        api_key = ExternalAPIKeyFactory()
        assert api_key.pk is not None
        assert len(api_key.key) == 64
        assert api_key.is_active is True
        assert api_key.project is not None
        assert api_key.default_assignee is not None

    def test_key_auto_generated_when_blank(self):
        api_key = ExternalAPIKeyFactory(key="")
        assert len(api_key.key) == 64

    def test_str_representation(self):
        api_key = ExternalAPIKeyFactory(name="Test Platform")
        assert str(api_key) == "Test Platform"


@pytest.mark.django_db
class TestIssueSourceFields:
    def test_issue_source_fields_default_null(self):
        issue = IssueFactory()
        assert issue.source is None
        assert issue.source_meta is None

    def test_issue_with_source_meta(self):
        meta = {
            "feedback_id": "FB001",
            "reporter": {"tenant_name": "Test Corp", "user_name": "张三"},
        }
        issue = IssueFactory(source="agent_platform", source_meta=meta)
        issue.refresh_from_db()
        assert issue.source == "agent_platform"
        assert issue.source_meta["feedback_id"] == "FB001"
        assert issue.source_meta["reporter"]["user_name"] == "张三"


@pytest.fixture
def api_key_obj():
    return ExternalAPIKeyFactory()


@pytest.fixture
def external_client(api_key_obj):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {api_key_obj.key}")
    return client


@pytest.mark.django_db
class TestAPIKeyAuthentication:
    def test_valid_key_authenticates(self, api_key_obj):
        from apps.external.authentication import APIKeyAuthentication

        factory = APIRequestFactory()
        request = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {api_key_obj.key}")
        auth = APIKeyAuthentication()
        user, auth_info = auth.authenticate(request)
        assert user == api_key_obj.default_assignee
        assert request.api_key == api_key_obj

    def test_invalid_key_returns_none(self):
        from apps.external.authentication import APIKeyAuthentication

        factory = APIRequestFactory()
        request = factory.get("/", HTTP_AUTHORIZATION="Bearer invalid_key_here")
        auth = APIKeyAuthentication()
        result = auth.authenticate(request)
        assert result is None

    def test_inactive_key_returns_none(self):
        from apps.external.authentication import APIKeyAuthentication

        inactive_key = ExternalAPIKeyFactory(is_active=False)
        factory = APIRequestFactory()
        request = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {inactive_key.key}")
        auth = APIKeyAuthentication()
        result = auth.authenticate(request)
        assert result is None

    def test_missing_header_returns_none(self):
        from apps.external.authentication import APIKeyAuthentication

        factory = APIRequestFactory()
        request = factory.get("/")
        auth = APIKeyAuthentication()
        result = auth.authenticate(request)
        assert result is None


@pytest.mark.django_db
class TestExternalIssueCreateSerializer:
    def test_valid_full_payload(self, site_settings):
        from apps.external.serializers import ExternalIssueCreateSerializer
        data = {
            "title": "测试问题",
            "type": "bug",
            "priority": "P1",
            "description": "详细描述",
            "module": "case_management",
            "source_feedback_id": "FB001",
            "reporter": {"tenant_name": "Test Corp", "user_name": "张三"},
            "context": {"page_url": "/test", "browser": "Chrome"},
            "attachments": [{"type": "screenshot", "url": "https://example.com/img.png"}],
        }
        serializer = ExternalIssueCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_minimal_payload(self, site_settings):
        from apps.external.serializers import ExternalIssueCreateSerializer
        data = {"title": "最简问题"}
        serializer = ExternalIssueCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_type_to_label_mapping(self, site_settings):
        from apps.external.serializers import ExternalIssueCreateSerializer
        for type_val, expected_label in [
            ("bug", "Bug"), ("BUG", "Bug"),
            ("feature", "需求"), ("功能建议", "需求"),
            ("improvement", "优化"), ("体验改进", "优化"),
        ]:
            data = {"title": "测试", "type": type_val}
            serializer = ExternalIssueCreateSerializer(data=data)
            assert serializer.is_valid(), serializer.errors
            assert expected_label in serializer.validated_data["_labels"]

    def test_module_appended_to_labels(self, site_settings):
        from apps.external.serializers import ExternalIssueCreateSerializer
        data = {"title": "测试", "type": "bug", "module": "case_management"}
        serializer = ExternalIssueCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert "Bug" in serializer.validated_data["_labels"]
        assert "case_management" in serializer.validated_data["_labels"]

    def test_default_priority(self, site_settings):
        from apps.external.serializers import ExternalIssueCreateSerializer
        data = {"title": "测试"}
        serializer = ExternalIssueCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data.get("priority", "P2") == "P2"


@pytest.mark.django_db
class TestExternalCreateIssue:
    def test_create_issue_full_payload(self, external_client, api_key_obj, site_settings):
        data = {
            "title": "案件导入页面上传Excel后无响应",
            "type": "bug",
            "priority": "P1",
            "description": "上传5MB的Excel文件后页面卡住不动",
            "module": "case_management",
            "source_feedback_id": "FB202604040001",
            "reporter": {
                "tenant_id": "T001", "tenant_name": "XX催收公司",
                "user_id": "U001", "user_name": "张三", "contact": "13800138000",
            },
            "context": {"page_url": "/case/import", "browser": "Chrome 120.0"},
            "attachments": [{"type": "screenshot", "url": "https://cdn.example.com/img.png"}],
        }
        resp = external_client.post("/api/external/issues/", data, format="json")
        assert resp.status_code == 201
        assert resp.data["title"] == "案件导入页面上传Excel后无响应"
        assert resp.data["status"] == "待分配"
        assert resp.data["priority"] == "P1"
        assert "issue_number" in resp.data

        # Verify the issue was created correctly
        from apps.issues.models import Issue
        issue = Issue.objects.get(pk=resp.data["id"])
        assert issue.source == "agent_platform"
        assert issue.project == api_key_obj.project
        assert issue.assignee is None
        assert issue.created_by == api_key_obj.default_assignee
        assert issue.reporter == "张三"
        assert issue.source_meta["feedback_id"] == "FB202604040001"
        assert issue.source_meta["reporter"]["user_name"] == "张三"
        assert "Bug" in issue.labels
        assert "case_management" in issue.labels

    def test_create_issue_minimal_payload(self, external_client, api_key_obj, site_settings):
        data = {"title": "最简问题"}
        resp = external_client.post("/api/external/issues/", data, format="json")
        assert resp.status_code == 201
        assert resp.data["status"] == "待分配"
        assert resp.data["priority"] == "P2"

    def test_duplicate_feedback_id_returns_409(self, external_client, api_key_obj, site_settings):
        data = {"title": "问题一", "source_feedback_id": "FB_DUP_001"}
        resp1 = external_client.post("/api/external/issues/", data, format="json")
        assert resp1.status_code == 201

        data2 = {"title": "问题二", "source_feedback_id": "FB_DUP_001"}
        resp2 = external_client.post("/api/external/issues/", data2, format="json")
        assert resp2.status_code == 409
        assert resp2.data["existing_issue_id"] == resp1.data["id"]

    def test_unauthenticated_returns_401(self, api_client, site_settings):
        resp = api_client.post("/api/external/issues/", {"title": "test"}, format="json")
        assert resp.status_code == 401


@pytest.mark.django_db
class TestExternalQueryIssue:
    def test_get_issue_by_id(self, external_client, api_key_obj, site_settings):
        issue = IssueFactory(
            source="agent_platform",
            source_meta={"feedback_id": "FB001"},
            project=api_key_obj.project,
        )
        resp = external_client.get(f"/api/external/issues/{issue.pk}/")
        assert resp.status_code == 200
        assert resp.data["id"] == issue.pk
        assert resp.data["source_feedback_id"] == "FB001"
        assert "issue_number" in resp.data

    def test_get_issue_wrong_project_returns_404(self, external_client, site_settings):
        issue = IssueFactory(source="agent_platform")  # different project
        resp = external_client.get(f"/api/external/issues/{issue.pk}/")
        assert resp.status_code == 404

    def test_get_non_external_issue_returns_404(self, external_client, api_key_obj, site_settings):
        issue = IssueFactory(project=api_key_obj.project)  # source is None
        resp = external_client.get(f"/api/external/issues/{issue.pk}/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestExternalListIssues:
    def test_list_issues_scoped_to_project(self, external_client, api_key_obj, site_settings):
        IssueFactory(source="agent_platform", project=api_key_obj.project)
        IssueFactory(source="agent_platform", project=api_key_obj.project)
        IssueFactory(source="agent_platform")  # different project
        resp = external_client.get("/api/external/issues/")
        assert resp.status_code == 200
        assert resp.data["count"] == 2

    def test_filter_by_feedback_id(self, external_client, api_key_obj, site_settings):
        IssueFactory(
            source="agent_platform",
            source_meta={"feedback_id": "FB_FIND_ME"},
            project=api_key_obj.project,
        )
        IssueFactory(
            source="agent_platform",
            source_meta={"feedback_id": "FB_OTHER"},
            project=api_key_obj.project,
        )
        resp = external_client.get("/api/external/issues/?feedback_id=FB_FIND_ME")
        assert resp.status_code == 200
        assert resp.data["count"] == 1

    def test_filter_by_status(self, external_client, api_key_obj, site_settings):
        IssueFactory(source="agent_platform", project=api_key_obj.project, status="待分配")
        IssueFactory(source="agent_platform", project=api_key_obj.project, status="进行中")
        resp = external_client.get("/api/external/issues/?status=待分配")
        assert resp.status_code == 200
        assert resp.data["count"] == 1

    def test_filter_by_priority(self, external_client, api_key_obj, site_settings):
        IssueFactory(source="agent_platform", project=api_key_obj.project, priority="P0")
        IssueFactory(source="agent_platform", project=api_key_obj.project, priority="P2")
        resp = external_client.get("/api/external/issues/?priority=P0")
        assert resp.status_code == 200
        assert resp.data["count"] == 1

    def test_pagination(self, external_client, api_key_obj, site_settings):
        for _ in range(25):
            IssueFactory(source="agent_platform", project=api_key_obj.project)
        resp = external_client.get("/api/external/issues/?page_size=10")
        assert resp.status_code == 200
        assert resp.data["count"] == 25
        assert len(resp.data["results"]) == 10


@pytest.mark.django_db
class TestExternalAPIDocs:
    def test_docs_endpoint_returns_spec(self, auth_client):
        resp = auth_client.get("/api/external/docs/")
        assert resp.status_code == 200
        assert resp.data["title"] == "DevTrack 外部 API 接口文档"
        assert resp.data["version"] == "v1"
        assert len(resp.data["endpoints"]) == 3
        methods = [e["method"] for e in resp.data["endpoints"]]
        assert "POST" in methods
        assert "GET" in methods

    def test_docs_endpoint_has_auth_info(self, auth_client):
        resp = auth_client.get("/api/external/docs/")
        assert resp.data["authentication"]["type"] == "Bearer Token"

    def test_docs_endpoint_requires_auth(self, api_client):
        resp = api_client.get("/api/external/docs/")
        assert resp.status_code in (401, 403)

    def test_docs_has_request_examples(self, auth_client):
        resp = auth_client.get("/api/external/docs/")
        create_endpoint = resp.data["endpoints"][0]
        assert create_endpoint["method"] == "POST"
        assert "example" in create_endpoint["request_body"]
        assert "title" in create_endpoint["request_body"]["example"]

    def test_docs_has_response_examples(self, auth_client):
        resp = auth_client.get("/api/external/docs/")
        create_endpoint = resp.data["endpoints"][0]
        assert len(create_endpoint["responses"]) >= 2
        assert create_endpoint["responses"][0]["status"] == 201


@pytest.mark.django_db
class TestExternalAPITestKey:
    def test_valid_key(self, external_client, api_key_obj):
        resp = external_client.post("/api/external/test-key/")
        assert resp.status_code == 200
        assert resp.data["valid"] is True
        assert resp.data["key_name"] == api_key_obj.name
        assert resp.data["project"] == api_key_obj.project.name

    def test_invalid_key(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer bad_key_here")
        resp = api_client.post("/api/external/test-key/")
        assert resp.status_code == 401
        assert resp.data["valid"] is False

    def test_no_key(self, api_client):
        resp = api_client.post("/api/external/test-key/")
        assert resp.status_code == 401
