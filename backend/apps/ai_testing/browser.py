from __future__ import annotations

import fnmatch
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

CONTROLLED_TOOLS = {
    "open_url",
    "observe_page",
    "click",
    "fill",
    "press",
    "wait_for_text",
    "assert_text",
    "take_screenshot",
    "finish_success",
    "finish_failure",
}

UNSAVED_DIALOG_TEXT_TOKENS = (
    "未保存",
    "放弃编辑",
    "关闭后将丢失",
    "确认离开",
    "内容将丢失",
    "discard",
    "unsaved",
    "leave without saving",
    "changes will be lost",
)
UNSAVED_DIALOG_STAY_TOKENS = (
    "继续编辑",
    "继续填写",
    "取消",
    "留在此页",
    "留在页面",
    "stay",
    "keep editing",
    "continue editing",
)
UNSAVED_DIALOG_DISCARD_TOKENS = (
    "放弃",
    "离开",
    "discard",
    "leave",
    "close without",
)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    if not text:
        return False
    folded = text.casefold()
    return any(token.casefold() in folded for token in tokens)


def _pick_dialog_button_target(buttons: list[dict[str, Any]], tokens: tuple[str, ...]) -> str:
    for button in buttons:
        if not isinstance(button, dict):
            continue
        candidate = _normalize_text(button.get("text") or button.get("ariaLabel") or button.get("name"))
        if candidate and _contains_any(candidate, tokens):
            return candidate
    return ""


def _build_unsaved_dialog_signal(*, dialogs: list[dict[str, Any]], visible_text: str) -> dict[str, Any]:
    for dialog in dialogs:
        if not isinstance(dialog, dict):
            continue
        dialog_text = _normalize_text(dialog.get("text"))
        buttons = dialog.get("buttons")
        if not isinstance(buttons, list):
            buttons = []
        if _contains_any(dialog_text, UNSAVED_DIALOG_TEXT_TOKENS):
            recover_target = _pick_dialog_button_target(buttons, UNSAVED_DIALOG_STAY_TOKENS)
            discard_target = _pick_dialog_button_target(buttons, UNSAVED_DIALOG_DISCARD_TOKENS)
            return {
                "detected": True,
                "dialog_text": dialog_text[:280],
                "recover_target": recover_target,
                "discard_target": discard_target,
            }

    return {
        "detected": False,
        "dialog_text": "",
        "recover_target": "",
        "discard_target": "",
    }


class BrowserRuntimeUnavailable(RuntimeError):
    """Playwright runtime is not installed or not available."""


class BrowserPolicyViolation(RuntimeError):
    """Action is blocked by environment policy."""


@dataclass
class ScreenshotPayload:
    file_name: str
    content: bytes
    mime_type: str = "image/png"


@dataclass
class BrowserToolResult:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    page_url: str = ""
    screenshot: ScreenshotPayload | None = None


class HeadlessBrowserSession:
    """Server-side controlled headless browser session."""

    def __init__(
        self,
        *,
        base_url: str,
        allowed_url_patterns: list[str] | None = None,
        allow_write_actions: bool = False,
        allow_dangerous_actions: bool = False,
        timeout_ms: int = 30000,
        headless: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.allowed_url_patterns = [p for p in (allowed_url_patterns or []) if p]
        self.allow_write_actions = allow_write_actions
        self.allow_dangerous_actions = allow_dangerous_actions
        self.timeout_ms = timeout_ms
        self.headless = headless

        self.console_logs: list[dict[str, Any]] = []
        self.network_errors: list[dict[str, Any]] = []

        self._playwright = None
        self._browser = None
        self._context = None
        self.page = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on runtime env
            raise BrowserRuntimeUnavailable(
                "playwright 未安装，无法启动服务端无头浏览器。"
            ) from exc

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = self._browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1440, "height": 900},
        )
        self.page = self._context.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        self.page.on("console", self._on_console)
        self.page.on("requestfailed", self._on_request_failed)
        return self

    def __exit__(self, exc_type, exc, tb):
        for obj in [self._context, self._browser, self._playwright]:
            try:
                if obj is not None:
                    obj.close() if hasattr(obj, "close") else obj.stop()
            except Exception:  # pragma: no cover - close failures are non-fatal
                logger.exception("ai-testing browser close error")
        return False

    def execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> BrowserToolResult:
        if tool_name not in CONTROLLED_TOOLS:
            return BrowserToolResult(ok=False, message=f"不支持的工具: {tool_name}")

        try:
            handler = getattr(self, f"_tool_{tool_name}")
            result = handler(tool_input or {})
            if result.page_url == "" and self.page is not None:
                result.page_url = self.page.url or ""
            return result
        except BrowserPolicyViolation as exc:
            return BrowserToolResult(ok=False, message=str(exc), page_url=self.page.url if self.page else "")
        except Exception as exc:
            return BrowserToolResult(ok=False, message=str(exc), page_url=self.page.url if self.page else "")

    def _on_console(self, message):
        try:
            self.console_logs.append(
                {
                    "type": message.type,
                    "text": message.text,
                    "location": message.location,
                }
            )
            if len(self.console_logs) > 200:
                self.console_logs = self.console_logs[-200:]
        except Exception:
            logger.exception("ai-testing console event parse failed")

    def _on_request_failed(self, request):
        try:
            self.network_errors.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                    "failure": request.failure or "",
                }
            )
            if len(self.network_errors) > 200:
                self.network_errors = self.network_errors[-200:]
        except Exception:
            logger.exception("ai-testing requestfailed parse failed")

    def _ensure_url_allowed(self, url: str):
        if not self.allowed_url_patterns:
            return
        for pattern in self.allowed_url_patterns:
            if fnmatch.fnmatch(url, pattern):
                return
        raise BrowserPolicyViolation(f"URL 不在白名单内: {url}")

    def _resolve_url(self, value: str) -> str:
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return urljoin(self.base_url + "/", value.lstrip("/"))

    def _dangerous_text_blocked(self, text: str) -> bool:
        if self.allow_dangerous_actions:
            return False
        lowered = text.lower()
        if re.search(r"\b(delete|remove|truncate|destroy|danger)\b", lowered):
            return True
        # Block SQL-like drop/destroy terms but avoid false positive on words such as "dropdown".
        if re.search(r"\bdrop\b", lowered) and "dropdown" not in lowered:
            return True
        return any(token in text for token in ("危险", "删除", "清空"))

    def _is_auth_field_target(self, target: str) -> bool:
        lowered = target.lower()
        auth_tokens = [
            "username",
            "user",
            "email",
            "password",
            "passwd",
            "otp",
            "token",
            "验证码",
            "账号",
            "密码",
        ]
        return any(token in lowered for token in auth_tokens)

    def _get_locator(self, target: str):
        target = (target or "").strip()
        if not target:
            raise ValueError("target 不能为空")

        if target.startswith("css="):
            return self.page.locator(target[4:]).first
        if target.startswith("xpath="):
            return self.page.locator(target).first
        if target.startswith("//"):
            return self.page.locator(f"xpath={target}").first
        if target.startswith("text="):
            return self.page.get_by_text(target[5:], exact=False).first

        safe_target = target.replace("\\", "\\\\").replace("'", "\\'")
        text_locator = self.page.get_by_text(target, exact=False).first
        if text_locator.count() > 0:
            return text_locator

        css_candidates = [
            f"[aria-label*='{safe_target}']",
            f"[placeholder*='{safe_target}']",
            f"input[name*='{safe_target}']",
            f"textarea[name*='{safe_target}']",
            f"select[name*='{safe_target}']",
            f"[data-testid*='{safe_target}']",
        ]
        for css in css_candidates:
            locator = self.page.locator(css).first
            if locator.count() > 0:
                return locator

        return self.page.locator(target).first

    def _get_click_locator(self, target: str):
        target = (target or "").strip()
        if not target:
            raise ValueError("target 不能为空")

        # Explicit selector modes keep original behavior except text=,
        # which should still prefer clickable controls.
        if target.startswith(("css=", "xpath=", "//")):
            return self._get_locator(target)
        if target.startswith("text="):
            text_target = target[5:].strip()
            if not text_target:
                raise ValueError("click text= 需要有效文本")
            clickable = self._get_clickable_text_locator(text_target)
            if clickable is not None:
                return clickable
            return self._get_locator(target)

        # Natural-language targets should prefer clickable controls, not generic text nodes.
        looks_like_selector = any(token in target for token in ["#", ".", "[", "]", ">", ":", "=", "//"])
        if not looks_like_selector:
            clickable = self._get_clickable_text_locator(target)
            if clickable is not None:
                return clickable

        return self._get_locator(target)

    def _get_clickable_text_locator(self, text_target: str):
        role_button = self.page.get_by_role("button", name=text_target, exact=False).first
        if role_button.count() > 0:
            return role_button

        role_link = self.page.get_by_role("link", name=text_target, exact=False).first
        if role_link.count() > 0:
            return role_link

        safe_target = text_target.replace("\\", "\\\\").replace('"', '\\"')
        css_candidates = [
            f'[role="button"]:has-text("{safe_target}")',
            f'button:has-text("{safe_target}")',
            f'a:has-text("{safe_target}")',
        ]
        for css in css_candidates:
            locator = self.page.locator(css).first
            if locator.count() > 0:
                return locator
        return None

    def _get_fill_locator(self, target: str):
        target = (target or "").strip()
        if not target:
            raise ValueError("target 不能为空")

        if target.startswith(("css=", "xpath=", "//")):
            return self._get_locator(target)

        label_text = target[5:].strip() if target.startswith("text=") else target
        safe_target = label_text.replace("\\", "\\\\").replace("'", "\\'")
        field_css_candidates = [
            f"input[aria-label*='{safe_target}']",
            f"textarea[aria-label*='{safe_target}']",
            f"[contenteditable='true'][aria-label*='{safe_target}']",
            f"input[placeholder*='{safe_target}']",
            f"textarea[placeholder*='{safe_target}']",
            f"input[name*='{safe_target}']",
            f"textarea[name*='{safe_target}']",
            f"select[name*='{safe_target}']",
            f"label:has-text('{safe_target}') + input",
            f"label:has-text('{safe_target}') + textarea",
            f"label:has-text('{safe_target}') + select",
            f"label:has-text('{safe_target}') ~ input",
            f"label:has-text('{safe_target}') ~ textarea",
            f"label:has-text('{safe_target}') ~ select",
        ]
        for css in field_css_candidates:
            locator = self.page.locator(css).first
            if locator.count() > 0:
                return locator

        return self._get_locator(target)

    def _tool_open_url(self, tool_input: dict[str, Any]) -> BrowserToolResult:
        raw_url = (tool_input.get("url") or "").strip()
        if not raw_url:
            raise ValueError("open_url 需要 url")
        url = self._resolve_url(raw_url)
        self._ensure_url_allowed(url)
        response = self.page.goto(url, wait_until="domcontentloaded")
        status_code = response.status if response else None
        return BrowserToolResult(
            ok=True,
            message=f"已打开 {url}",
            data={"status_code": status_code},
            page_url=self.page.url,
        )

    def _tool_observe_page(self, tool_input: dict[str, Any]) -> BrowserToolResult:
        max_text = int(tool_input.get("max_text", 1200) or 1200)
        max_elements = int(tool_input.get("max_elements", 40) or 40)
        title = self.page.title()
        text = self.page.inner_text("body")[:max_text]
        elements = self.page.evaluate(
            """
            ({ limit }) => {
              const nodes = Array.from(
                document.querySelectorAll(
                  'button,a,input,textarea,select,[role="button"],[data-testid]'
                )
              ).slice(0, limit);
              return nodes.map((el) => ({
                tag: el.tagName.toLowerCase(),
                id: el.id || "",
                name: el.getAttribute("name") || "",
                role: el.getAttribute("role") || "",
                type: el.getAttribute("type") || "",
                placeholder: el.getAttribute("placeholder") || "",
                ariaLabel: el.getAttribute("aria-label") || "",
                text: (el.innerText || el.value || "").trim().slice(0, 80),
                testid: el.getAttribute("data-testid") || ""
              }));
            }
            """,
            {"limit": max_elements},
        )
        dialogs = self.page.evaluate(
            """
            () => {
              const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (!style) return true;
                if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
              };

              const textOf = (el) => (el?.innerText || el?.textContent || "").replace(/\\s+/g, " ").trim();
              const candidates = Array.from(
                document.querySelectorAll(
                  '[role="alertdialog"],[role="dialog"],.ant-modal,.el-dialog,.modal,[class*="dialog"],[class*="Dialog"]'
                )
              );
              const out = [];
              const seen = new Set();

              for (const node of candidates) {
                if (!isVisible(node)) continue;
                const text = textOf(node);
                if (!text) continue;
                const key = text.slice(0, 160);
                if (seen.has(key)) continue;
                seen.add(key);

                const buttons = Array.from(
                  node.querySelectorAll('button,[role="button"],a,input[type="button"],input[type="submit"]')
                )
                  .filter((el) => isVisible(el))
                  .map((el) => ({
                    tag: (el.tagName || "").toLowerCase(),
                    text: textOf(el).slice(0, 80),
                    ariaLabel: (el.getAttribute("aria-label") || "").slice(0, 80),
                    name: (el.getAttribute("name") || "").slice(0, 80),
                  }))
                  .filter((item) => item.text || item.ariaLabel || item.name)
                  .slice(0, 10);

                out.push({
                  text: text.slice(0, 360),
                  role: node.getAttribute("role") || "",
                  buttons,
                });
                if (out.length >= 6) break;
              }
              return out;
            }
            """
        )
        unsaved_dialog = _build_unsaved_dialog_signal(dialogs=dialogs if isinstance(dialogs, list) else [], visible_text=text)
        return BrowserToolResult(
            ok=True,
            message="页面观察完成",
            data={
                "title": title,
                "visible_text": text,
                "interactive_elements": elements,
                "dialogs": dialogs if isinstance(dialogs, list) else [],
                "unsaved_changes_dialog": unsaved_dialog,
            },
            page_url=self.page.url,
        )

    def _tool_click(self, tool_input: dict[str, Any]) -> BrowserToolResult:
        target = (tool_input.get("target") or "").strip()
        if not target:
            raise ValueError("click 需要 target")
        if self._dangerous_text_blocked(target):
            raise BrowserPolicyViolation(f"危险操作已拦截: click({target})")
        locator = self._get_click_locator(target)
        try:
            locator.click()
            return BrowserToolResult(ok=True, message=f"已点击: {target}", page_url=self.page.url)
        except Exception as exc:
            msg = str(exc)
            # Common UI case: a modal backdrop intercepts pointer events.
            if "intercepts pointer events" not in msg:
                raise
            # Do not force-click and mark success: that can produce false positives and endless loops.
            # We only try a lightweight recovery (Esc + normal click). If it still fails, surface the error.
            try:
                self.page.keyboard.press("Escape")
                locator.click(timeout=min(8000, self.timeout_ms))
                return BrowserToolResult(
                    ok=True,
                    message=f"已点击(遮罩恢复): {target}",
                    data={"recovered_from_overlay": True},
                    page_url=self.page.url,
                )
            except Exception as retry_exc:
                raise RuntimeError(
                    f"点击被遮罩拦截，未执行强制点击: {target}; 原始错误: {msg}; 重试后: {retry_exc}"
                ) from retry_exc

    def _tool_fill(self, tool_input: dict[str, Any]) -> BrowserToolResult:
        target = (tool_input.get("target") or "").strip()
        if not self.allow_write_actions and not self._is_auth_field_target(target):
            raise BrowserPolicyViolation("当前环境未启用写操作，已拦截 fill")
        value = str(tool_input.get("value") or "")
        if not target:
            raise ValueError("fill 需要 target")
        if self._dangerous_text_blocked(target):
            raise BrowserPolicyViolation(f"危险操作已拦截: fill({target})")
        locator = self._get_fill_locator(target)
        locator.fill(value)
        masked = f"{len(value)} chars" if value else ""
        return BrowserToolResult(
            ok=True,
            message=f"已输入: {target}",
            data={"value_masked": masked},
            page_url=self.page.url,
        )

    def _tool_press(self, tool_input: dict[str, Any]) -> BrowserToolResult:
        key = (tool_input.get("key") or "").strip()
        if not key:
            raise ValueError("press 需要 key")
        self.page.keyboard.press(key)
        return BrowserToolResult(ok=True, message=f"已按键: {key}", page_url=self.page.url)

    def _tool_wait_for_text(self, tool_input: dict[str, Any]) -> BrowserToolResult:
        text = (tool_input.get("text") or "").strip()
        timeout_ms = int(tool_input.get("timeout_ms") or self.timeout_ms)
        if not text:
            raise ValueError("wait_for_text 需要 text")
        self.page.get_by_text(text, exact=False).first.wait_for(timeout=timeout_ms)
        return BrowserToolResult(ok=True, message=f"已等待文本出现: {text}", page_url=self.page.url)

    def _tool_assert_text(self, tool_input: dict[str, Any]) -> BrowserToolResult:
        text = (tool_input.get("text") or "").strip()
        timeout_ms = int(tool_input.get("timeout_ms") or self.timeout_ms)
        if not text:
            raise ValueError("assert_text 需要 text")
        locator = self.page.get_by_text(text, exact=False).first
        locator.wait_for(timeout=timeout_ms)
        return BrowserToolResult(ok=True, message=f"断言通过: {text}", page_url=self.page.url)

    def _tool_take_screenshot(self, tool_input: dict[str, Any]) -> BrowserToolResult:
        reason = (tool_input.get("reason") or "step").strip()
        step_index = int(tool_input.get("step_index") or 0)
        safe_reason = re.sub(r"[^0-9A-Za-z_.-]+", "_", reason)[:40] or "step"
        file_name = f"run_{step_index:03d}_{safe_reason}.png"
        content = self.page.screenshot(full_page=True, type="png")
        return BrowserToolResult(
            ok=True,
            message=f"已截图: {reason}",
            page_url=self.page.url,
            screenshot=ScreenshotPayload(file_name=file_name, content=content),
        )

    def _tool_finish_success(self, tool_input: dict[str, Any]) -> BrowserToolResult:
        summary = (tool_input.get("summary") or "执行成功").strip()
        return BrowserToolResult(ok=True, message=summary, data={"finished": "success"}, page_url=self.page.url)

    def _tool_finish_failure(self, tool_input: dict[str, Any]) -> BrowserToolResult:
        reason = (tool_input.get("reason") or "执行失败").strip()
        return BrowserToolResult(ok=False, message=reason, data={"finished": "failure"}, page_url=self.page.url)
