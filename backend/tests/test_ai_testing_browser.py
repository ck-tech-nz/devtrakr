from apps.ai_testing.browser import HeadlessBrowserSession


class _FakeLocator:
    def __init__(self, source: str, hit: bool = False):
        self.source = source
        self._hit = hit

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self._hit else 0


class _FakePage:
    def __init__(self, *, role_hits=None, css_hits=None, text_hits=None):
        self.role_hits = role_hits or {}
        self.css_hits = css_hits or {}
        self.text_hits = text_hits or {}
        self.calls = []

    def get_by_role(self, role, *, name, exact=False):
        self.calls.append(("get_by_role", role, name, exact))
        return _FakeLocator(f"role:{role}:{name}", bool(self.role_hits.get((role, name))))

    def locator(self, selector):
        self.calls.append(("locator", selector))
        return _FakeLocator(f"css:{selector}", bool(self.css_hits.get(selector)))

    def get_by_text(self, text, *, exact=False):
        self.calls.append(("get_by_text", text, exact))
        return _FakeLocator(f"text:{text}", bool(self.text_hits.get(text)))


def _build_session(page):
    session = HeadlessBrowserSession(base_url="https://example.com")
    session.page = page
    return session


def test_click_text_target_prefers_button_role_locator():
    page = _FakePage(
        role_hits={("button", "新建问题"): True},
        text_hits={"新建问题": True},
    )
    session = _build_session(page)

    locator = session._get_click_locator("text=新建问题")

    assert locator.source == "role:button:新建问题"
    assert not any(call[0] == "get_by_text" for call in page.calls)


def test_click_text_target_falls_back_to_link_role_locator():
    page = _FakePage(
        role_hits={("link", "创建Issue"): True},
        text_hits={"创建Issue": True},
    )
    session = _build_session(page)

    locator = session._get_click_locator("text=创建Issue")

    assert locator.source == "role:link:创建Issue"


def test_click_text_target_falls_back_to_text_locator_when_no_clickable_control():
    page = _FakePage(text_hits={"新建问题": True})
    session = _build_session(page)

    locator = session._get_click_locator("text=新建问题")

    assert locator.source == "text:新建问题"
    assert any(call[0] == "get_by_text" for call in page.calls)


def test_observe_page_detects_unsaved_changes_dialog_signal():
    class _ObserveFakePage:
        def __init__(self):
            self.url = "https://example.com/issues"

        def title(self):
            return "Issues"

        def inner_text(self, selector):
            assert selector == "body"
            return "放弃编辑？表单中有未保存的内容，关闭后将丢失。"

        def evaluate(self, script, arg=None):
            if isinstance(arg, dict) and "limit" in arg:
                return [
                    {"tag": "button", "id": "", "name": "", "role": "button", "type": "", "placeholder": "", "ariaLabel": "", "text": "关闭", "testid": ""},
                ]
            return [
                {
                    "text": "放弃编辑？ 表单中有未保存的内容，关闭后将丢失。确定要放弃吗？",
                    "role": "alertdialog",
                    "buttons": [
                        {"tag": "button", "text": "继续编辑", "ariaLabel": "", "name": ""},
                        {"tag": "button", "text": "放弃", "ariaLabel": "", "name": ""},
                    ],
                }
            ]

    session = _build_session(_ObserveFakePage())
    result = session._tool_observe_page({"max_text": 1200, "max_elements": 40})

    assert result.ok is True
    signal = result.data["unsaved_changes_dialog"]
    assert signal["detected"] is True
    assert signal["recover_target"] == "继续编辑"
    assert signal["discard_target"] == "放弃"


def test_dangerous_text_blocking_allows_dropdown_and_blocks_drop_statement():
    session = HeadlessBrowserSession(base_url="https://example.com")

    assert session._dangerous_text_blocked("css=#reka-dropdown-menu-trigger-v-1-2") is False
    assert session._dangerous_text_blocked("drop table issues") is True


def test_fill_target_prefers_input_like_locators_over_plain_text_node():
    page = _FakePage(
        css_hits={"input[placeholder*='标题']": True},
        text_hits={"标题": True},
    )
    session = _build_session(page)

    locator = session._get_fill_locator("text=标题")

    assert locator.source == "css:input[placeholder*='标题']"
    assert not any(call[0] == "get_by_text" for call in page.calls)
