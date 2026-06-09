import factory
from faker import Faker
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from apps.settings.models import SiteSettings
from apps.projects.models import Project, ProjectMember
from apps.issues.models import Issue, Activity
from apps.repos.models import Repo, GitHubIssue, Commit, GitAuthorAlias
from apps.ai.models import LLMConfig, Prompt, Analysis
from apps.tools.models import Attachment
from apps.uptime.models import UptimeMonitor, UptimeCheck
from django.utils import timezone as tz

fake = Faker("zh_CN")
User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"{fake.user_name()}_{n}")
    name = factory.LazyFunction(lambda: fake.name())
    email = factory.LazyFunction(lambda: fake.email())
    password = factory.PostGenerationMethodCall("set_password", "testpass123")


class SiteSettingsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SiteSettings
        django_get_or_create = ("id",)

    id = 1
    labels = {
        "前端": {"foreground": "#ffffff", "background": "#0075ca", "description": "前端相关问题"},
        "后端": {"foreground": "#ffffff", "background": "#e99695", "description": "后端相关问题"},
        "Bug": {"foreground": "#ffffff", "background": "#d73a4a", "description": "程序错误"},
        "优化": {"foreground": "#ffffff", "background": "#a2eeef", "description": ""},
        "需求": {"foreground": "#ffffff", "background": "#7057ff", "description": ""},
        "文档": {"foreground": "#ffffff", "background": "#0075ca", "description": ""},
        "CI/CD": {"foreground": "#ffffff", "background": "#e4e669", "description": ""},
        "安全": {"foreground": "#ffffff", "background": "#d73a4a", "description": ""},
        "性能": {"foreground": "#ffffff", "background": "#f9d0c4", "description": ""},
        "UI/UX": {"foreground": "#ffffff", "background": "#bfd4f2", "description": ""},
    }
    priorities = ["P0", "P1", "P2", "P3"]
    issue_statuses = ["未计划", "待分配", "待确认", "进行中", "已解决", "已发布", "已关闭"]


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    name = factory.LazyFunction(lambda: fake.catch_phrase())
    description = factory.LazyFunction(lambda: fake.paragraph())
    status = "进行中"


class GroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Group
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"角色{n}")


class ProjectMemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjectMember

    project = factory.SubFactory(ProjectFactory)
    user = factory.SubFactory(UserFactory)
    role = None
    is_manager = False


class IssueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Issue

    project = factory.SubFactory(ProjectFactory)
    repo = None
    title = factory.LazyFunction(lambda: fake.sentence())
    description = factory.LazyFunction(lambda: fake.paragraph())
    priority = factory.Iterator(["P0", "P1", "P2", "P3"])
    status = "待分配"
    labels = factory.LazyFunction(lambda: [fake.random_element(["前端", "后端", "Bug"])])
    created_by = factory.SubFactory(UserFactory)


class ActivityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Activity

    user = factory.SubFactory(UserFactory)
    issue = factory.SubFactory(IssueFactory)
    action = "created"
    detail = ""


class RepoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Repo

    name = factory.LazyFunction(lambda: fake.word() + "-" + fake.word())
    full_name = factory.LazyAttribute(lambda o: f"org/{o.name}")
    url = factory.LazyAttribute(lambda o: f"https://github.com/{o.full_name}")
    description = factory.LazyFunction(lambda: fake.sentence())
    default_branch = "main"
    language = factory.Iterator(["Python", "TypeScript", "Go", "Java"])
    stars = factory.LazyFunction(lambda: fake.random_int(0, 500))
    status = "在线"


class GitHubIssueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GitHubIssue

    repo = factory.SubFactory(RepoFactory)
    github_id = factory.Sequence(lambda n: n + 1)
    title = factory.LazyFunction(lambda: fake.sentence())
    body = factory.LazyFunction(lambda: fake.paragraph())
    state = "open"
    labels = factory.LazyFunction(lambda: [fake.word()])
    assignees = factory.LazyFunction(lambda: [fake.user_name()])
    github_created_at = factory.LazyFunction(tz.now)
    github_updated_at = factory.LazyFunction(tz.now)
    synced_at = factory.LazyFunction(tz.now)


class CommitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Commit

    repo = factory.SubFactory(RepoFactory)
    hash = factory.LazyFunction(lambda: fake.sha1())
    author_name = factory.LazyFunction(lambda: fake.name())
    author_email = factory.LazyFunction(lambda: fake.email())
    date = factory.LazyFunction(tz.now)
    message = factory.LazyFunction(lambda: fake.sentence())
    additions = factory.LazyFunction(lambda: fake.random_int(1, 200))
    deletions = factory.LazyFunction(lambda: fake.random_int(0, 100))
    files_changed = factory.LazyFunction(lambda: [f"src/{fake.file_name()}"])


class GitAuthorAliasFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GitAuthorAlias

    repo = factory.SubFactory(RepoFactory)
    author_email = factory.LazyFunction(lambda: fake.email())
    author_name = factory.LazyFunction(lambda: fake.name())
    user = None


class LLMConfigFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LLMConfig

    name = factory.Sequence(lambda n: f"LLM Config {n}")
    api_key = "sk-test-key"
    base_url = ""
    supports_json_mode = True
    is_default = False
    is_active = True


class PromptFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Prompt

    slug = factory.Sequence(lambda n: f"analysis_type_{n}")
    name = factory.Sequence(lambda n: f"Prompt {n}")
    system_prompt = "You are a helpful assistant. Return JSON only."
    user_prompt_template = "Analyze: {total_issues} total issues."
    llm_model = "gpt-4o"
    temperature = 0.3
    llm_config = factory.SubFactory(LLMConfigFactory)
    is_active = True


class AnalysisFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Analysis

    analysis_type = "team_insights"
    triggered_by = "page_open"
    issue = None
    status = "pending"
    data_hash = ""
    input_context = factory.LazyFunction(dict)
    prompt_snapshot = factory.LazyFunction(dict)


class AttachmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Attachment

    uploaded_by = factory.SubFactory(UserFactory)
    file_name = factory.Sequence(lambda n: f"screenshot_{n}.png")
    file_key = factory.Sequence(lambda n: f"2026/03/27/{n:04d}.png")
    file_url = factory.LazyAttribute(lambda o: f"http://minio:9000/devtrack-uploads/{o.file_key}")
    file_size = 102400
    mime_type = "image/png"


from apps.kpi.models import KPISnapshot, ImprovementPlan, ActionItem, ActionItemComment


class KPISnapshotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = KPISnapshot

    user = factory.SubFactory(UserFactory)
    period_start = factory.LazyFunction(lambda: tz.now().date().replace(day=1))
    period_end = factory.LazyFunction(lambda: tz.now().date())
    issue_metrics = factory.LazyFunction(lambda: {"assigned_count": 10, "resolved_count": 8})
    commit_metrics = factory.LazyFunction(lambda: {"total_commits": 50})
    scores = factory.LazyFunction(lambda: {"efficiency": 70, "output": 75, "quality": 80, "capability": 65, "growth": 50, "overall": 72})
    rankings = factory.LazyFunction(lambda: {"overall_rank": 1, "total_developers": 1})
    suggestions = factory.LazyFunction(lambda: {"profile": "均衡发展型", "shortcomings": [], "trends": []})
    computed_at = factory.LazyFunction(tz.now)


class ImprovementPlanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ImprovementPlan

    user = factory.SubFactory(UserFactory)
    period = factory.LazyFunction(lambda: tz.now().strftime("%Y-%m"))
    status = "draft"
    source_kpi_scores = factory.LazyFunction(lambda: {"efficiency": 70, "output": 75, "overall": 72})


class ActionItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ActionItem

    plan = factory.SubFactory(ImprovementPlanFactory)
    source = "ai_generated"
    dimension = "efficiency"
    title = factory.Sequence(lambda n: f"改进行动 {n}")
    description = "具体改进建议"
    measurable_target = "达到目标值"
    points = 20
    priority = "medium"
    status = "pending"


class ActionItemCommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ActionItemComment

    action_item = factory.SubFactory(ActionItemFactory)
    author = factory.SubFactory(UserFactory)
    content = "完成情况说明"


from apps.settings.models import ExternalAPIKey, generate_api_key


class ExternalAPIKeyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExternalAPIKey

    name = factory.Sequence(lambda n: f"External Platform {n}")
    key = factory.LazyFunction(generate_api_key)
    project = factory.SubFactory(ProjectFactory)
    default_assignee = factory.SubFactory(UserFactory)
    is_active = True


from apps.notifications.models import Notification, NotificationRecipient, Bulletin


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    notification_type = "system"
    title = factory.LazyFunction(lambda: fake.sentence())
    content = factory.LazyFunction(lambda: fake.paragraph())
    target_type = "user"


class NotificationRecipientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NotificationRecipient

    notification = factory.SubFactory(NotificationFactory)
    user = factory.SubFactory(UserFactory)
    is_read = False
    is_deleted = False


class BulletinFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Bulletin

    category = "quote"
    content = factory.LazyFunction(lambda: fake.sentence())
    source = ""
    is_active = True
    sort_order = factory.Sequence(lambda n: n)


class UptimeMonitorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UptimeMonitor

    project = factory.SubFactory(ProjectFactory)
    name = factory.Sequence(lambda n: f"monitor-{n}")
    url = factory.Sequence(lambda n: f"https://example{n}.com/health")
    method = "GET"
    expected_status = "200"
    interval_minutes = 1
    timeout_secs = 20
    is_enabled = True


class UptimeCheckFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UptimeCheck

    monitor = factory.SubFactory(UptimeMonitorFactory)
    checked_at = factory.LazyFunction(tz.now)
    is_up = True
    status_code = 200
    response_ms = 100
