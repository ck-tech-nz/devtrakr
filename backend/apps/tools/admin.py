from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin

from . import services
from .models import Attachment


class AttachmentUploadForm(forms.ModelForm):
    """后台「添加附件」用的表单: 选文件后保存即上传到对象存储并生成记录。"""

    upload = forms.FileField(
        label="选择文件",
        help_text="保存后自动上传到对象存储并生成附件记录 (≤20MB)",
    )

    class Meta:
        model = Attachment
        fields = ["upload", "file_name", "uploaded_by"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 文件名/归属可留空 — 文件名取原始文件名, 归属默认当前管理员。
        self.fields["file_name"].required = False
        self.fields["file_name"].help_text = "留空则使用上传文件的原始文件名"
        self.fields["uploaded_by"].required = False

    def clean_upload(self):
        f = self.cleaned_data.get("upload")
        if f:
            services.validate_upload(f)  # 类型/大小不合法时抛 ValidationError
        return f


@admin.register(Attachment)
class AttachmentAdmin(ModelAdmin):
    list_display = ["file_name", "mime_type", "file_size_kb", "uploaded_by", "created_at"]
    list_filter = ["mime_type", "created_at"]
    search_fields = ["file_name", "uploaded_by__name"]
    raw_id_fields = ["uploaded_by"]

    def get_form(self, request, obj=None, **kwargs):
        # 仅「添加」页换成上传表单; 「修改」页沿用默认表单 (附件落库后只读元数据)。
        if obj is None:
            kwargs["form"] = AttachmentUploadForm
        return super().get_form(request, obj, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        return ["id", "file_key", "file_url", "file_size", "mime_type", "created_at"]

    def save_model(self, request, obj, form, change):
        upload = form.cleaned_data.get("upload")
        if upload is not None:
            if not obj.uploaded_by_id:
                obj.uploaded_by = request.user
            data = services.upload_to_storage(upload)
            obj.file_name = obj.file_name or data["file_name"]
            obj.file_key = data["file_key"]
            obj.file_url = data["file_url"]
            obj.file_size = data["file_size"]
            obj.mime_type = data["mime_type"]
            obj.content_hash = data["content_hash"]
        super().save_model(request, obj, form, change)

    @admin.display(description="大小 (KB)")
    def file_size_kb(self, obj):
        return f"{obj.file_size // 1024} KB"
