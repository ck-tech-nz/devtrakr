import uuid
from django.conf import settings
from django.db import models


class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="attachments",
    )
    file_name = models.CharField(max_length=255, verbose_name="文件名")
    file_key = models.CharField(max_length=500, unique=True, verbose_name="存储键")
    file_url = models.URLField(max_length=1000, verbose_name="访问地址")
    file_size = models.PositiveBigIntegerField(verbose_name="文件大小")
    mime_type = models.CharField(max_length=100, verbose_name="类型")
    # sha256 of raw bytes; 上传时填入, 用于同 user 重复内容去重 (避免 LLM 多看一份同图)
    # 老数据为空字符串, 无法匹配 - dedup 只对新上传生效
    content_hash = models.CharField(max_length=64, blank=True, default="", db_index=True, verbose_name="内容哈希")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "附件"
        verbose_name_plural = "附件"
        ordering = ["-created_at"]

    def __str__(self):
        return self.file_name

    @property
    def is_image(self):
        return self.mime_type.startswith("image/")
