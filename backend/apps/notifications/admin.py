from django.contrib import admin, messages
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseRedirect
from django.urls import reverse
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action
from .models import Notification, NotificationRecipient
from .services import RemotePublishError, generate_recipients, publish_notification_to_remote


class RecipientInline(TabularInline):
    model = NotificationRecipient
    extra = 0
    readonly_fields = ("user",  "read_at")


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ("title", "notification_type", "target_type", "is_draft", "created_at")
    list_filter = ("notification_type", "target_type", "is_draft")
    search_fields = ("title",)
    inlines = [RecipientInline]
    actions_detail = ["publish_draft", "publish_to_test", "publish_to_prod"]

    def save_model(self, request, obj, form, change):
        request._notification_was_draft = None
        if change:
            try:
                request._notification_was_draft = Notification.objects.get(pk=obj.pk).is_draft
            except Notification.DoesNotExist:
                pass
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        was_draft = getattr(request, "_notification_was_draft", None)
        publish_now = (not change and not obj.is_draft) or (
            change and was_draft is True and not obj.is_draft
        )
        if publish_now:
            generate_recipients(obj)

    @action(description="发布草稿")
    def publish_draft(self, request, object_id):
        notification = Notification.objects.get(pk=object_id)
        if not notification.is_draft:
            messages.warning(request, "该通知不是草稿,无需发布")
        else:
            notification.is_draft = False
            notification.save(update_fields=["is_draft"])
            count = generate_recipients(notification)
            messages.success(request, f"已发布,接收人 {count}")
        return HttpResponseRedirect(
            reverse("admin:notifications_notification_change", args=[object_id]),
        )

    def _publish_to(self, request, object_id, env):
        notification = Notification.objects.get(pk=object_id)
        try:
            result = publish_notification_to_remote(notification, env=env)
        except (ImproperlyConfigured, RemotePublishError) as e:
            messages.error(request, f"发布到 {env} 失败:{e}")
        else:
            messages.success(
                request,
                f"已发布到 {env},远端 ID {result.get('id')},接收人 {result.get('recipients')}",
            )
        return HttpResponseRedirect(
            reverse("admin:notifications_notification_change", args=[object_id]),
        )

    @action(description="发布到 test")
    def publish_to_test(self, request, object_id):
        return self._publish_to(request, object_id, env="test")

    @action(description="发布到 prod")
    def publish_to_prod(self, request, object_id):
        return self._publish_to(request, object_id, env="prod")


@admin.register(NotificationRecipient)
class NotificationRecipientAdmin(ModelAdmin):
    list_display = ("notification", "user", "is_read", "is_deleted")
    list_filter = ("is_read", "is_deleted")
