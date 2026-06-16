from rest_framework import serializers
from .models import Repo, GitHubIssue, GitAuthorAlias, PullRequest


class GitHubIssueBriefSerializer(serializers.ModelSerializer):
    repo_full_name = serializers.CharField(source="repo.full_name", read_only=True)

    class Meta:
        model = GitHubIssue
        fields = [
            "id", "repo", "repo_full_name", "github_id", "title",
            "state", "labels", "assignees",
            "github_created_at", "github_updated_at",
        ]
        read_only_fields = fields


class GitHubIssueDetailSerializer(serializers.ModelSerializer):
    repo_full_name = serializers.CharField(source="repo.full_name", read_only=True)
    repo_name = serializers.CharField(source="repo.name", read_only=True)

    class Meta:
        model = GitHubIssue
        fields = [
            "id", "repo", "repo_full_name", "repo_name", "github_id", "title", "body",
            "state", "labels", "assignees",
            "github_created_at", "github_updated_at", "github_closed_at", "synced_at",
        ]
        read_only_fields = fields


class GitAuthorAliasSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True, default=None)

    class Meta:
        model = GitAuthorAlias
        fields = ["id", "author_email", "author_name", "user", "user_name"]
        read_only_fields = ["id", "author_email", "author_name"]


class RepoSerializer(serializers.ModelSerializer):
    open_issues_count = serializers.IntegerField(read_only=True, default=0)
    closed_issues_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Repo
        # github_token 故意不包含在内，防止凭据泄露
        fields = [
            "id", "name", "full_name", "url", "description",
            "default_branch", "language", "stars", "status",
            "connected_at", "last_synced_at",
            "open_issues_count", "closed_issues_count",
            "clone_status", "clone_error", "current_branch", "cloned_at",
        ]
        read_only_fields = ["id", "connected_at", "last_synced_at", "clone_status", "clone_error", "current_branch", "cloned_at"]


class PullRequestSerializer(serializers.ModelSerializer):
    repo_full_name = serializers.CharField(source="repo.full_name", read_only=True)
    linked_issues = serializers.SerializerMethodField()

    class Meta:
        model = PullRequest
        fields = [
            "id", "repo", "repo_full_name", "number", "title", "state",
            "merged_at", "closed_at", "base_branch", "head_branch",
            "author_login", "author_avatar", "html_url",
            "github_created_at", "github_updated_at", "linked_issues",
        ]
        read_only_fields = fields

    def get_linked_issues(self, obj):
        from apps.issues.models import Issue
        refs = obj.linked_issues or []
        ids = [r.get("id") for r in refs if r.get("id") is not None]
        if not ids:
            return []
        issues = {
            i.id: i
            for i in Issue.objects.filter(pk__in=ids).only("id", "title", "status")
        }
        result = []
        for r in refs:
            issue = issues.get(r.get("id"))
            if issue:
                result.append({
                    "id": issue.id,
                    "title": issue.title,
                    "status": issue.status,
                    "ref": r.get("ref"),
                    "source": r.get("source"),
                })
        return result
