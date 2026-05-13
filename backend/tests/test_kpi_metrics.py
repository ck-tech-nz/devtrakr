import pytest
from datetime import date, timedelta
from django.contrib.auth.models import Group
from django.utils import timezone
from apps.kpi.models import KPISnapshot
from apps.kpi.metrics import (
    compute_commit_metrics,
    compute_issue_metrics,
    compute_workload_metrics,
)
from apps.kpi.scoring import compute_tier
from apps.kpi.services import KPIService
from tests.factories import (
    UserFactory,
    ProjectFactory,
    IssueFactory,
    ActivityFactory,
    RepoFactory,
    CommitFactory,
    GitAuthorAliasFactory,
)

pytestmark = pytest.mark.django_db


class TestKPISnapshotModel:
    def test_create_snapshot(self):
        user = UserFactory()
        snap = KPISnapshot.objects.create(
            user=user,
            period_start="2026-04-01",
            period_end="2026-04-15",
            issue_metrics={"assigned_count": 10, "resolved_count": 8},
            commit_metrics={"total_commits": 50},
            scores={"efficiency": 80, "output": 75, "quality": 90, "capability": 70, "growth": 60, "overall": 77},
            rankings={"overall_rank": 2, "total_developers": 5},
            suggestions={"profile": "均衡发展型"},
            computed_at=timezone.now(),
        )
        assert snap.pk is not None
        assert str(snap) == f"{user} | 2026-04-01 ~ 2026-04-15"

    def test_unique_constraint(self):
        user = UserFactory()
        KPISnapshot.objects.create(
            user=user, period_start="2026-04-01", period_end="2026-04-15",
            computed_at=timezone.now(),
        )
        with pytest.raises(Exception):
            KPISnapshot.objects.create(
                user=user, period_start="2026-04-01", period_end="2026-04-15",
                computed_at=timezone.now(),
            )


# ---------------------------------------------------------------------------
# Issue Metrics Tests
# ---------------------------------------------------------------------------


class TestIssueMetrics:
    def test_basic_issue_metrics(self):
        """3 个已解决 + 1 个未解决，验证计数、比率、平均小时、优先级拆分。"""
        user = UserFactory()
        project = ProjectFactory()
        base = timezone.make_aware(timezone.datetime(2026, 4, 5, 10, 0))

        # 3 个已解决（P0, P1, P2），各花 24h
        for i, prio in enumerate(["P0", "P1", "P2"]):
            issue = IssueFactory(
                project=project,
                assignee=user,
                priority=prio,
                status="已解决",
                created_by=user,
            )
            # 手动设置 created_at / resolved_at 确保精确
            issue.created_at = base + timedelta(days=i)
            issue.resolved_at = base + timedelta(days=i, hours=24)
            issue.save(update_fields=["created_at", "resolved_at"])
            # 给每个 issue 加一条 Activity
            ActivityFactory(user=user, issue=issue, action="comment")

        # 1 个未解决（P3）
        unresolved = IssueFactory(
            project=project,
            assignee=user,
            priority="P3",
            status="进行中",
            created_by=user,
        )
        unresolved.created_at = base + timedelta(days=3)
        unresolved.save(update_fields=["created_at"])

        result = compute_issue_metrics(user, date(2026, 4, 1), date(2026, 4, 30))

        assert result["assigned_count"] == 4
        assert result["resolved_count"] == 3
        assert result["resolution_rate"] == 0.75
        assert result["avg_resolution_hours"] == 24.0

        # 优先级拆分
        pb = result["priority_breakdown"]
        assert pb["P0"]["assigned"] == 1
        assert pb["P0"]["resolved"] == 1
        assert pb["P0"]["avg_hours"] == 24.0
        assert pb["P3"]["assigned"] == 1
        assert pb["P3"]["resolved"] == 0

        # weighted_issue_value > 0（每个 resolved 都有 24h 和 1 activity）
        assert result["weighted_issue_value"] > 0

        # daily / weekly averages
        assert result["daily_resolved_avg"] > 0
        assert result["weekly_resolved_avg"] > 0

    def test_issue_metrics_empty(self):
        """没有任何 Issue 时返回全零。"""
        user = UserFactory()
        result = compute_issue_metrics(user, date(2026, 4, 1), date(2026, 4, 30))

        assert result["assigned_count"] == 0
        assert result["resolved_count"] == 0
        assert result["resolution_rate"] == 0
        assert result["avg_resolution_hours"] == 0
        assert result["weighted_issue_value"] == 0
        assert result["as_helper_count"] == 0
        for prio in ("P0", "P1", "P2", "P3"):
            assert result["priority_breakdown"][prio]["assigned"] == 0

    def test_helper_count(self):
        """验证 as_helper_count: 用户作为协助人但不是负责人。"""
        user = UserFactory()
        assignee = UserFactory()
        project = ProjectFactory()
        base = timezone.make_aware(timezone.datetime(2026, 4, 5, 10, 0))

        # Issue 1: user 是协助人，assignee 是别人
        issue1 = IssueFactory(
            project=project,
            assignee=assignee,
            priority="P1",
            status="进行中",
            created_by=assignee,
        )
        issue1.created_at = base
        issue1.save(update_fields=["created_at"])
        issue1.helpers.add(user)

        # Issue 2: user 既是 assignee 又是 helper —— 不应计入 as_helper_count
        issue2 = IssueFactory(
            project=project,
            assignee=user,
            priority="P2",
            status="待处理",
            created_by=assignee,
        )
        issue2.created_at = base + timedelta(days=1)
        issue2.save(update_fields=["created_at"])
        issue2.helpers.add(user)

        result = compute_issue_metrics(user, date(2026, 4, 1), date(2026, 4, 30))
        assert result["as_helper_count"] == 1


# ---------------------------------------------------------------------------
# Commit Metrics Tests
# ---------------------------------------------------------------------------


class TestCommitMetrics:
    def test_basic_commit_metrics(self):
        """5 个 feat + 1 个 fix（同文件 72h 内），验证全部字段。"""
        user = UserFactory()
        repo = RepoFactory(clone_status="cloned")
        email = "dev@example.com"
        GitAuthorAliasFactory(repo=repo, user=user, author_email=email)

        base = timezone.make_aware(timezone.datetime(2026, 4, 5, 10, 0))
        shared_file = "src/app.py"

        # 5 个 feat commits
        for i in range(5):
            CommitFactory(
                repo=repo,
                author_email=email,
                author_name=user.name,
                message=f"feat: add feature {i}",
                date=base + timedelta(hours=i * 2),
                additions=30 + i * 10,
                deletions=5 + i,
                files_changed=[shared_file, f"src/module_{i}.ts"],
            )

        # 1 个 fix commit（同一文件，48h 后 — 仍在 72h 窗口内）
        CommitFactory(
            repo=repo,
            author_email=email,
            author_name=user.name,
            message="fix: resolve bug in app",
            date=base + timedelta(hours=48),
            additions=5,
            deletions=3,
            files_changed=[shared_file],
        )

        result = compute_commit_metrics(user, date(2026, 4, 1), date(2026, 4, 30))

        assert result["total_commits"] == 6
        assert result["additions"] > 0
        assert result["deletions"] > 0
        assert result["lines_changed"] == result["additions"] + result["deletions"]

        # Commit 大小分布
        dist = result["commit_size_distribution"]
        assert dist["small"] + dist["medium"] + dist["large"] == 6

        # 文件类型广度 — py + ts = 2
        assert result["file_type_breadth"] >= 2

        # 工作节奏
        assert len(result["work_rhythm"]["by_hour"]) == 24
        assert len(result["work_rhythm"]["by_weekday"]) == 7

        # Conventional commit ratio
        assert result["conventional_ratio"] == 1.0

        # commit_type_distribution
        assert result["commit_type_distribution"]["feat"] == 5
        assert result["commit_type_distribution"]["fix"] == 1

        # refactor_ratio — 无 refactor
        assert result["refactor_ratio"] == 0

        # self_introduced_bug_rate > 0（feat commit 48h 后同文件有 fix）
        assert result["self_introduced_bug_rate"] > 0

        # avg_commit_size
        assert result["avg_commit_size"] > 0

        # repo_coverage
        assert len(result["repo_coverage"]) == 1
        assert result["repo_coverage"][0]["repo_id"] == repo.id
        assert result["repo_coverage"][0]["commits"] == 6

    def test_commit_metrics_no_commits(self):
        """无 commit 返回空指标。"""
        user = UserFactory()

        result = compute_commit_metrics(user, date(2026, 4, 1), date(2026, 4, 30))

        assert result["total_commits"] == 0
        assert result["additions"] == 0
        assert result["deletions"] == 0
        assert result["lines_changed"] == 0
        assert result["self_introduced_bug_rate"] == 0
        assert result["churn_rate"] == 0
        assert result["commit_size_distribution"] == {"small": 0, "medium": 0, "large": 0}
        assert result["avg_commit_size"] == 0
        assert result["file_type_breadth"] == 0
        assert result["work_rhythm"]["by_hour"] == [0] * 24
        assert result["work_rhythm"]["by_weekday"] == [0] * 7
        assert result["refactor_ratio"] == 0
        assert result["commit_type_distribution"] == {}
        assert result["conventional_ratio"] == 0
        assert result["repo_coverage"] == []


# ---------------------------------------------------------------------------
# KPI Service Tests
# ---------------------------------------------------------------------------


class TestWorkloadMetrics:
    def test_empty_user(self):
        user = UserFactory()
        result = compute_workload_metrics(user, date(2026, 4, 1), date(2026, 4, 30))
        assert result["completed_count"] == 0
        assert result["estimated_earnings"] == 0
        assert result["rework_count"] == 0
        assert result["breakdown"] == []

    def test_piece_rate_count_tier_at_boundary(self):
        """前 20 个走 ¥100，第 21 个起 ¥160（estimated_hours < 4h 走小型）。"""
        user = UserFactory()
        project = ProjectFactory()
        base = timezone.make_aware(timezone.datetime(2026, 4, 5, 10, 0))

        for i in range(22):
            issue = IssueFactory(
                project=project, assignee=user, priority="P2",
                status="已解决", created_by=user,
                estimated_hours=2.0, actual_hours=1.0,
            )
            issue.created_at = base + timedelta(hours=i)
            issue.resolved_at = base + timedelta(hours=i, minutes=30)
            issue.save(update_fields=["created_at", "resolved_at"])

        result = compute_workload_metrics(user, date(2026, 4, 1), date(2026, 4, 30))
        assert result["completed_count"] == 22
        assert result["small_count"] == 22
        # 20 * 100 + 2 * 160 = 2320
        assert result["estimated_earnings"] == 2320

    def test_hour_bracket_medium_and_large(self):
        """规模由 estimated_hours 决定:4-16h 中型 ¥250,≥ 16h 大型 ¥600。"""
        user = UserFactory()
        project = ProjectFactory()
        base = timezone.make_aware(timezone.datetime(2026, 4, 5, 10, 0))

        # 中型: estimated 8h, actual 9h (略超)
        # 大型: estimated 20h, actual 18h (低于预计)
        for i, (est, actual) in enumerate([(8.0, 9.0), (20.0, 18.0)]):
            issue = IssueFactory(
                project=project, assignee=user, priority="P1",
                status="已解决", created_by=user,
                estimated_hours=est, actual_hours=actual,
            )
            issue.created_at = base + timedelta(days=i)
            issue.resolved_at = base + timedelta(days=i, hours=actual)
            issue.save(update_fields=["created_at", "resolved_at"])

        result = compute_workload_metrics(user, date(2026, 4, 1), date(2026, 4, 30))
        assert result["medium_count"] == 1
        assert result["large_count"] == 1
        assert result["estimated_earnings"] == 250 + 600

    def test_delay_metrics(self):
        """avg_delay_ratio / total_delay_hours / total_overrun_hours / over_estimate_count。"""
        user = UserFactory()
        project = ProjectFactory()
        base = timezone.make_aware(timezone.datetime(2026, 4, 5, 10, 0))

        # 工单 A: 预计 4h, 实际 8h → ratio 2.0, +4h
        # 工单 B: 预计 4h, 实际 2h → ratio 0.5, -2h (提前完成)
        for i, (est, actual) in enumerate([(4.0, 8.0), (4.0, 2.0)]):
            issue = IssueFactory(
                project=project, assignee=user, priority="P2",
                status="已解决", created_by=user,
                estimated_hours=est, actual_hours=actual,
            )
            issue.created_at = base + timedelta(days=i)
            issue.resolved_at = base + timedelta(days=i, hours=actual)
            issue.save(update_fields=["created_at", "resolved_at"])

        result = compute_workload_metrics(user, date(2026, 4, 1), date(2026, 4, 30))
        assert result["avg_delay_ratio"] == 1.25
        assert result["over_estimate_count"] == 1
        # 总延期 = 只算超出的 4h
        assert result["total_delay_hours"] == 4.0
        # 净偏差 = 4 + (-2) = 2h
        assert result["total_overrun_hours"] == 2.0

    def test_rework_detection_within_protection_window(self):
        """已解决后 7 天内被改回进行中应计入 rework_count。"""
        user = UserFactory()
        project = ProjectFactory()
        base = timezone.make_aware(timezone.datetime(2026, 4, 5, 10, 0))

        issue = IssueFactory(
            project=project, assignee=user, priority="P1",
            status="进行中", created_by=user,
        )
        issue.created_at = base
        issue.save(update_fields=["created_at"])

        # user 标记已解决
        resolve_act = ActivityFactory(
            user=user, issue=issue, action="resolved",
            detail="状态从 进行中 改为 已解决",
        )
        resolve_act.created_at = base + timedelta(hours=2)
        resolve_act.save(update_fields=["created_at"])

        # 2 天后被改回进行中（仍在 7 天保护期内）
        regression = ActivityFactory(
            user=user, issue=issue, action="updated",
            detail="状态从 已解决 改为 进行中",
        )
        regression.created_at = base + timedelta(days=2)
        regression.save(update_fields=["created_at"])

        # 把 issue 的 resolved_at 也搬到本期内
        issue.resolved_at = base + timedelta(hours=2)
        issue.status = "已解决"
        issue.save(update_fields=["resolved_at", "status"])

        result = compute_workload_metrics(user, date(2026, 4, 1), date(2026, 4, 30))
        assert result["rework_count"] == 1

    def test_rework_outside_window_not_counted(self):
        """超过 7 天保护期的回退不计入。"""
        user = UserFactory()
        project = ProjectFactory()
        base = timezone.make_aware(timezone.datetime(2026, 4, 1, 10, 0))

        issue = IssueFactory(
            project=project, assignee=user, priority="P2",
            status="已解决", created_by=user,
        )
        issue.created_at = base
        issue.resolved_at = base + timedelta(hours=1)
        issue.save(update_fields=["created_at", "resolved_at"])

        ra = ActivityFactory(
            user=user, issue=issue, action="resolved",
            detail="状态从 进行中 改为 已解决",
        )
        ra.created_at = base + timedelta(hours=1)
        ra.save(update_fields=["created_at"])

        # 10 天后才回退，超出 7 天窗口
        rg = ActivityFactory(
            user=user, issue=issue, action="updated",
            detail="状态从 已解决 改为 进行中",
        )
        rg.created_at = base + timedelta(days=10)
        rg.save(update_fields=["created_at"])

        result = compute_workload_metrics(user, date(2026, 4, 1), date(2026, 4, 30))
        assert result["rework_count"] == 0


class TestSettlement:
    def test_settle_freezes_price_at_resolve_time(self):
        """改 piece_rate_config 后已结算工单的金额不变。"""
        from apps.kpi.settlement import settle_issue
        from apps.kpi.models import KPIScoringConfig

        user = UserFactory()
        project = ProjectFactory()
        issue = IssueFactory(
            project=project, assignee=user, priority="P2",
            status="已解决", created_by=user,
            estimated_hours=4.0,
        )
        issue.resolved_at = timezone.now()
        issue.save(update_fields=["resolved_at"])

        # 用默认配置结算 (4h → 小型 → ¥100)
        payload = settle_issue(issue)
        assert payload["price"] == 100
        assert payload["size"] == "小型"

        # 之后改配置: 小型梯度改 ¥999
        cfg = KPIScoringConfig.get_solo()
        new = dict(cfg.piece_rate_config)
        new["count_tiers"] = [{"max_count": None, "price": 999}]
        cfg.piece_rate_config = new
        cfg.save()

        # KPI 计算应该还是用 ¥100,因为已锁定
        result = compute_workload_metrics(
            user, date(2026, 1, 1), date(2030, 12, 31)
        )
        assert result["estimated_earnings"] == 100
        assert result["breakdown"][0]["settled"] is True
        assert result["breakdown"][0]["price"] == 100

    def test_resolve_via_api_locks_settlement(self, auth_client, site_settings):
        """通过 PATCH 把状态改成已解决,settlement 自动写入。"""
        user = UserFactory()
        issue = IssueFactory(status="进行中", estimated_hours=2.0, assignee=user)
        response = auth_client.patch(
            f"/api/issues/{issue.id}/", {"status": "已解决"}
        )
        assert response.status_code == 200
        issue.refresh_from_db()
        assert issue.settlement is not None
        assert issue.settlement["estimated_hours"] == 2.0
        assert issue.settlement["price"] > 0

    def test_reopen_does_not_resettle(self):
        """重修不重新结算 (避免双倍计价)。"""
        from apps.kpi.settlement import settle_issue
        user = UserFactory()
        issue = IssueFactory(
            assignee=user, status="已解决",
            estimated_hours=2.0,
        )
        issue.resolved_at = timezone.now()
        issue.save(update_fields=["resolved_at"])
        first = settle_issue(issue)
        first_price = first["price"]

        # 改 estimated_hours 后再次调用 settle_issue
        issue.estimated_hours = 10.0
        issue.save(update_fields=["estimated_hours"])
        again = settle_issue(issue)
        assert again["price"] == first_price  # 不重算


class TestTier:
    def test_bronze_for_low_score(self):
        t = compute_tier(20)
        assert t["key"] == "bronze"
        assert t["next_key"] == "silver"

    def test_gold_at_threshold(self):
        t = compute_tier(72)
        assert t["key"] == "gold"
        assert t["label"] == "黄金"

    def test_master_at_top(self):
        t = compute_tier(98)
        assert t["key"] == "master"
        assert t["next_key"] is None


class TestKPIService:
    def test_refresh_computes_snapshots(self, site_settings):
        group, _ = Group.objects.get_or_create(name="开发者")
        user1 = UserFactory()
        user1.groups.add(group)
        user2 = UserFactory()
        user2.groups.add(group)
        project = ProjectFactory()

        for u in (user1, user2):
            IssueFactory(
                project=project, assignee=u, priority="P1",
                status="已解决", created_by=UserFactory(),
                resolved_at=timezone.now(), created_at=timezone.now() - timedelta(hours=10),
            )

        start = date(2026, 1, 1)
        end = date(2026, 12, 31)
        result = KPIService().refresh(start, end, role="开发者")

        assert result["user_count"] == 2
        assert KPISnapshot.objects.count() == 2

        snap = KPISnapshot.objects.filter(user=user1).first()
        assert snap is not None
        assert snap.scores["overall"] >= 0
        assert snap.rankings["total_developers"] == 2
        assert snap.suggestions["profile"]

    def test_refresh_updates_existing_snapshot(self, site_settings):
        group, _ = Group.objects.get_or_create(name="开发者")
        user = UserFactory()
        user.groups.add(group)

        start = date(2026, 4, 1)
        end = date(2026, 4, 15)
        KPIService().refresh(start, end, role="开发者")
        assert KPISnapshot.objects.count() == 1

        KPIService().refresh(start, end, role="开发者")
        assert KPISnapshot.objects.count() == 1
