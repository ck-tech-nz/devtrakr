from apps.settings.models import SiteSettings


def get_effective_default_project(user):
    """Return the project that should default-select for this user.

    Priority: user's own default_project → SiteSettings.default_project → None.
    Safe with AnonymousUser (returns None).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if user.default_project_id:
        return user.default_project
    return SiteSettings.get_solo().default_project
