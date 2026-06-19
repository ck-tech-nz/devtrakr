import random

from django.conf import settings

# 内置头像 id 白名单,需与前端 useAvatars.ts 的 avatarGroups 保持一致
AVATAR_CHOICES = [
    # 极客风格(SVG)
    "terminal-hacker",
    "robot",
    "bug-monster",
    "code-cat",
    "cpu-brain",
    "wifi-wizard",
    "binary-ghost",
    "docker-whale",
    "git-octopus",
    "code-ninja",
    "keyboard-warrior",
    "stack-overflow",
    "404-alien",
    "firewall-guard",
    "one-up-mushroom",
    "recursion-owl",
    "rubber-duck",
    "infinite-coffee",
    "sudo-penguin",
    "null-pointer",
    # 卡通插画(flaticon PNG)
    "fox",
    "bear",
    "bear-2",
    "lion",
    "crocodile",
    "giraffe",
    "squirrel",
    "wild-boar",
    "cow",
    "bee",
    "man",
    "man-2",
    "man-3",
    "woman",
    "woman-2",
    "woman-3",
    "planet-earth",
    "leaf",
    "plant-pot",
    "eco-friendly",
    "laptop",
    "online-training",
    "listening",
    "shovel",
    "ninja",
]


def random_avatar():
    return random.choice(AVATAR_CHOICES)


# 上传头像允许的图片扩展名(与 tools.storage 的 EXT_TO_MIME 图片项一致)
_AVATAR_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def is_valid_avatar(value: str) -> bool:
    """头像值合法的判定:空串 / 内置头像 id / 本站上传的图片 URL。

    上传 URL 必须以 MINIO_PUBLIC_URL 前缀开头(防止指向任意外部地址),
    且以图片扩展名结尾(防止把头像指向上传的 PDF/文档等非图片附件)。
    """
    if not value:
        return True
    if value in AVATAR_CHOICES:
        return True
    prefix = settings.MINIO_PUBLIC_URL.rstrip("/") + "/"
    if value.startswith(prefix):
        return value.rsplit("?", 1)[0].lower().endswith(_AVATAR_IMAGE_EXTS)
    return False
