import logging

from celery import shared_task

from .models import Repo
from .services import RepoCloneService, GitHubSyncService

logger = logging.getLogger(__name__)


@shared_task(ignore_result=False)
def pull_all_repos():
    """Pull latest code for all cloned repos."""
    for repo in Repo.objects.filter(clone_status="cloned"):
        try:
            RepoCloneService().clone_or_pull(repo)
        except Exception as e:
            logger.error("Failed to pull repo %s: %s", repo.full_name, e)


@shared_task(ignore_result=False)
def sync_all_repos():
    """Sync GitHub issues and pull requests for all repos with tokens."""
    service = GitHubSyncService()
    for repo in Repo.objects.exclude(github_token=""):
        try:
            service.sync_repo(repo)
            service.sync_pull_requests(repo)
        except Exception as e:
            logger.error("Failed to sync repo %s: %s", repo.full_name, e)
