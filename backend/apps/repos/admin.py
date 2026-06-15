from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Repo, GitHubIssue, Commit, GitAuthorAlias, PullRequest


@admin.register(Repo)
class RepoAdmin(ModelAdmin):
    list_display = ("full_name", "language", "stars", "status", "last_synced_at", "connected_at")
    readonly_fields = ("connected_at", "last_synced_at")


@admin.register(GitHubIssue)
class GitHubIssueAdmin(ModelAdmin):
    list_display = ("repo", "github_id", "title", "state", "synced_at")
    readonly_fields = (
        "repo", "github_id", "title", "body", "state", "labels",
        "assignees", "github_created_at", "github_updated_at",
        "github_closed_at", "synced_at",
    )
    list_filter = ("state", "repo")
    search_fields = ("title",)


@admin.register(Commit)
class CommitAdmin(ModelAdmin):
    list_display = ("repo", "hash_short", "author_name", "date", "message_short")
    list_filter = ("repo",)
    search_fields = ("hash", "author_name", "message")
    readonly_fields = (
        "repo", "hash", "author_name", "author_email", "date",
        "message", "additions", "deletions", "files_changed",
    )

    @admin.display(description="哈希")
    def hash_short(self, obj):
        return obj.hash[:7]

    @admin.display(description="信息")
    def message_short(self, obj):
        return obj.message[:60]


@admin.register(GitAuthorAlias)
class GitAuthorAliasAdmin(ModelAdmin):
    list_display = ("repo", "author_name", "author_email", "user")
    list_filter = ("repo",)
    search_fields = ("author_name", "author_email")
    autocomplete_fields = ("user",)


@admin.register(PullRequest)
class PullRequestAdmin(ModelAdmin):
    list_display = ("repo", "number", "title", "state", "author_login", "github_created_at")
    list_filter = ("state", "repo")
    search_fields = ("title", "author_login")
    readonly_fields = (
        "repo", "number", "title", "body", "state", "merged_at", "closed_at",
        "base_branch", "head_branch", "author_login", "author_avatar", "html_url",
        "github_created_at", "github_updated_at", "synced_at", "linked_issues",
    )
