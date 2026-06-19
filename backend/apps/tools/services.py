import hashlib

from django.core.exceptions import ValidationError

from . import storage

MAX_SIZE = 20 * 1024 * 1024  # 20MB

# Mirror this allowlist with frontend/app/components/MarkdownEditor.vue (ALLOWED_TYPES + EXTENSION_FALLBACK).
ALLOWED_TYPES = {
    # Images
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    # PDF
    "application/pdf",
    # Word
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # Excel
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # PowerPoint
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # Text / data
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    # Archive
    "application/zip",
    "application/x-zip-compressed",
}

# Extensions that are allowed even when the browser reports an unusual MIME type
# (e.g. some browsers report .md as text/plain or empty).
EXTENSION_FALLBACK = {
    "md", "txt", "csv", "json", "zip",
}


def sha256_of_uploaded(file) -> str:
    """流式读完上传文件算 sha256; 读完后 seek(0) 让后续 storage 写入仍能读到字节。
    Django 的 UploadedFile 内部可能是临时磁盘文件或内存, 都支持 seek。"""
    h = hashlib.sha256()
    for chunk in file.chunks():
        h.update(chunk)
    file.seek(0)
    return h.hexdigest()


def is_allowed(file) -> bool:
    if file.content_type in ALLOWED_TYPES:
        return True
    name = file.name or ""
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        if ext in EXTENSION_FALLBACK:
            return True
    return False


def validate_upload(file) -> None:
    """类型 / 大小 校验。不合法时抛 ValidationError (供 admin 表单展示错误)。"""
    if not is_allowed(file):
        raise ValidationError(f"不支持的文件类型: {file.content_type}")
    if file.size > MAX_SIZE:
        raise ValidationError("文件大小超过限制 (20MB)")


def upload_to_storage(file) -> dict:
    """校验 + 写入 MinIO, 返回可直接赋给 Attachment 的字段值 (不落库)。

    供 admin 后台直接上传文件使用 — admin 走 Django 正常的 add 流程建记录,
    所以这里只负责存储 + 算出字段, 不做去重 (去重逻辑在 API 上传里按 user 处理)。
    """
    validate_upload(file)
    content_hash = sha256_of_uploaded(file)
    url, key = storage.upload_image(file)
    return {
        "file_name": file.name,
        "file_key": key,
        "file_url": url,
        "file_size": file.size,
        "mime_type": file.content_type,
        "content_hash": content_hash,
    }
