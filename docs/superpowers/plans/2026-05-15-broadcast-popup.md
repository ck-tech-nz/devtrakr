# Broadcast Popup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a user enters the authenticated app shell, surface each unread broadcast notification as a sequential blocking popup that only the `知道了` button can dismiss; on dismissal, mark the broadcast read so it never pops again.

**Architecture:** Backend gains a one-line `?notification_type=` filter on the existing `NotificationListView`. Frontend extends the existing `useDialog().alert()` primitive with `htmlBody` (markdown-rendered HTML) and `persistent` (blocks backdrop/Esc dismiss) options, adds Markdown-body scoped styles to `AppDialog.vue`, and introduces a `useBroadcastPopup` composable that fetches unread broadcasts on mount and shows them one-by-one. The trigger lives in `layouts/default.vue` and uses a `useState` single-fire guard so navigation within `/app/*` never re-fires it.

**Tech Stack:** Django 5 + DRF; Nuxt 4 + Vue 3 + TypeScript + Nuxt UI; `markdown-it` via the existing `useMentionMarkdown` composable; `pytest-django` + `factory-boy`.

**Reference spec:** [docs/superpowers/specs/2026-05-15-broadcast-popup-design.md](../specs/2026-05-15-broadcast-popup-design.md)

---

## File Structure

**Modify:**
- `backend/apps/notifications/views.py` — add `notification_type` query-param filter to `NotificationListView.get_queryset` (3 lines).
- `backend/tests/test_notifications.py` — append one test case for the new filter.
- `frontend/app/composables/useDialog.ts` — extend `AlertOptions` + `DialogState` with `htmlBody`/`persistent` and propagate them in `alert()`.
- `frontend/app/components/AppDialog.vue` — branch body rendering on `state.htmlBody`, gate dismiss handlers on `state.persistent`, add scroll cap + scoped `.dialog-markdown` styles.
- `frontend/app/layouts/default.vue` — call `useBroadcastPopup().start()` on mount.

**Create:**
- `frontend/app/composables/useBroadcastPopup.ts` — single-fire fetch + queue + sequential `alert()` + `markRead`.

Each file has one clear responsibility: `useDialog` owns the dialog state primitive, `AppDialog` owns the rendering, `useBroadcastPopup` owns the broadcast-specific workflow, the layout owns the entry-point wiring, the backend view owns the filter contract.

---

## Task 1: Backend `notification_type` filter

**Files:**
- Modify: `backend/apps/notifications/views.py` (around line 22–31)
- Modify: `backend/tests/test_notifications.py` (append one test inside `class TestNotificationList`)

- [ ] **Step 1: Write the failing test**

Open `backend/tests/test_notifications.py`. Inside `class TestNotificationList:` (after the existing `test_unauthenticated` method, before the class ends), append:

```python
    def test_filter_by_notification_type(self, auth_client, auth_user):
        from tests.factories import NotificationFactory, NotificationRecipientFactory

        bc = NotificationFactory(notification_type="broadcast", title="release notes")
        NotificationRecipientFactory(notification=bc, user=auth_user)
        sys = NotificationFactory(notification_type="system", title="system thing")
        NotificationRecipientFactory(notification=sys, user=auth_user)
        mention = NotificationFactory(notification_type="mention", title="someone @ed you")
        NotificationRecipientFactory(notification=mention, user=auth_user)

        response = auth_client.get("/api/notifications/?notification_type=broadcast")
        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["title"] == "release notes"
```

The `NotificationFactory` and `NotificationRecipientFactory` are re-imported inside the test to make it self-contained even though the top of the file already imports them — harmless and explicit. (You can also rely on the existing module-level imports if you prefer.)

- [ ] **Step 2: Run the test to verify it fails**

From `backend/`:

```bash
uv run pytest tests/test_notifications.py::TestNotificationList::test_filter_by_notification_type -v
```

Expected: FAIL — without the backend filter, all three notifications are returned, so `count == 3 != 1`.

- [ ] **Step 3: Implement the filter**

Open `backend/apps/notifications/views.py`. Find `NotificationListView.get_queryset` (around line 22-31). It currently reads:

```python
    def get_queryset(self):
        qs = Notification.objects.filter(
            recipients__user=self.request.user,
            recipients__is_deleted=False,
            is_draft=False,
        ).select_related("source_user", "source_issue").distinct()
        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            qs = qs.filter(recipients__is_read=is_read.lower() == "true")
        return qs.order_by("-created_at")
```

Insert the new filter right after the `is_read` block, before the `return`:

```python
    def get_queryset(self):
        qs = Notification.objects.filter(
            recipients__user=self.request.user,
            recipients__is_deleted=False,
            is_draft=False,
        ).select_related("source_user", "source_issue").distinct()
        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            qs = qs.filter(recipients__is_read=is_read.lower() == "true")
        notif_type = self.request.query_params.get("notification_type")
        if notif_type:
            qs = qs.filter(notification_type=notif_type)
        return qs.order_by("-created_at")
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run pytest tests/test_notifications.py::TestNotificationList::test_filter_by_notification_type -v
```

Expected: PASS.

Also run the full test_notifications file to make sure nothing regressed:

```bash
uv run pytest tests/test_notifications.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/notifications/views.py backend/tests/test_notifications.py
git commit -m "feat(notifications): add notification_type query-param filter"
```

---

## Task 2: Extend `useDialog().alert()` API with `htmlBody` + `persistent`

**Files:**
- Modify: `frontend/app/composables/useDialog.ts`

This task only extends the composable. `AppDialog.vue` is updated in Task 3 to consume the new fields. Splitting them keeps each commit small.

- [ ] **Step 1: Update the type definitions**

Open `frontend/app/composables/useDialog.ts`. Find `AlertOptions` and `DialogState`. Currently:

```ts
export type AlertOptions = {
  title?: string
  message: string
  confirmText?: string
  color?: DialogColor
  icon?: string
}

type DialogState = {
  open: boolean
  mode: 'confirm' | 'alert'
  title: string
  message: string
  confirmText: string
  cancelText: string
  color: DialogColor
  icon: string
  resolve: ((v: boolean) => void) | null
}
```

Update them so `message` becomes optional, and add `htmlBody` + `persistent`:

```ts
export type AlertOptions = {
  title?: string
  message?: string
  htmlBody?: string
  persistent?: boolean
  confirmText?: string
  color?: DialogColor
  icon?: string
}

type DialogState = {
  open: boolean
  mode: 'confirm' | 'alert'
  title: string
  message: string
  htmlBody: string
  persistent: boolean
  confirmText: string
  cancelText: string
  color: DialogColor
  icon: string
  resolve: ((v: boolean) => void) | null
}
```

- [ ] **Step 2: Update `defaultState`**

Find the existing `defaultState` factory:

```ts
const defaultState = (): DialogState => ({
  open: false,
  mode: 'confirm',
  title: '',
  message: '',
  confirmText: '确认',
  cancelText: '取消',
  color: 'primary',
  icon: '',
  resolve: null,
})
```

Add the two new fields with safe defaults:

```ts
const defaultState = (): DialogState => ({
  open: false,
  mode: 'confirm',
  title: '',
  message: '',
  htmlBody: '',
  persistent: false,
  confirmText: '确认',
  cancelText: '取消',
  color: 'primary',
  icon: '',
  resolve: null,
})
```

- [ ] **Step 3: Update the `alert()` function to write the new fields**

Find the existing `alert()` function:

```ts
  function alert(opts: AlertOptions | string): Promise<void> {
    if (state.value.resolve) state.value.resolve(false)
    const o: AlertOptions = typeof opts === 'string' ? { message: opts } : opts
    return new Promise<void>((resolve) => {
      state.value = {
        open: true,
        mode: 'alert',
        title: o.title || '提示',
        message: o.message,
        confirmText: o.confirmText || '知道了',
        cancelText: '',
        color: o.color || 'primary',
        icon: o.icon || (o.color === 'error' ? 'i-heroicons-x-circle' : o.color === 'warning' ? 'i-heroicons-exclamation-triangle' : o.color === 'success' ? 'i-heroicons-check-circle' : 'i-heroicons-information-circle'),
        resolve: () => resolve(),
      }
    })
  }
```

Update it to populate `htmlBody`, `persistent`, and to coerce `message` to a string (since the type is now optional):

```ts
  function alert(opts: AlertOptions | string): Promise<void> {
    if (state.value.resolve) state.value.resolve(false)
    const o: AlertOptions = typeof opts === 'string' ? { message: opts } : opts
    return new Promise<void>((resolve) => {
      state.value = {
        open: true,
        mode: 'alert',
        title: o.title || '提示',
        message: o.message || '',
        htmlBody: o.htmlBody || '',
        persistent: o.persistent === true,
        confirmText: o.confirmText || '知道了',
        cancelText: '',
        color: o.color || 'primary',
        icon: o.icon || (o.color === 'error' ? 'i-heroicons-x-circle' : o.color === 'warning' ? 'i-heroicons-exclamation-triangle' : o.color === 'success' ? 'i-heroicons-check-circle' : 'i-heroicons-information-circle'),
        resolve: () => resolve(),
      }
    })
  }
```

- [ ] **Step 4: Update `confirm()` to populate the new fields with safe defaults**

Find `confirm()`:

```ts
  function confirm(opts: ConfirmOptions | string): Promise<boolean> {
    if (state.value.resolve) state.value.resolve(false)
    const o: ConfirmOptions = typeof opts === 'string' ? { message: opts } : opts
    return new Promise((resolve) => {
      state.value = {
        open: true,
        mode: 'confirm',
        title: o.title || '请确认',
        message: o.message,
        confirmText: o.confirmText || '确认',
        cancelText: o.cancelText || '取消',
        color: o.color || 'primary',
        icon: o.icon || (o.color === 'error' ? 'i-heroicons-exclamation-triangle' : ''),
        resolve,
      }
    })
  }
```

Update to set `htmlBody: ''` and `persistent: false` so existing `confirm()` callers see no behavior change:

```ts
  function confirm(opts: ConfirmOptions | string): Promise<boolean> {
    if (state.value.resolve) state.value.resolve(false)
    const o: ConfirmOptions = typeof opts === 'string' ? { message: opts } : opts
    return new Promise((resolve) => {
      state.value = {
        open: true,
        mode: 'confirm',
        title: o.title || '请确认',
        message: o.message,
        htmlBody: '',
        persistent: false,
        confirmText: o.confirmText || '确认',
        cancelText: o.cancelText || '取消',
        color: o.color || 'primary',
        icon: o.icon || (o.color === 'error' ? 'i-heroicons-exclamation-triangle' : ''),
        resolve,
      }
    })
  }
```

- [ ] **Step 5: Type-check the frontend**

From `frontend/`:

```bash
npx nuxi typecheck
```

Expected: no NEW errors caused by your edits. Pre-existing errors in unrelated files may persist; that's fine.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/composables/useDialog.ts
git commit -m "feat(useDialog): add htmlBody and persistent options to alert()"
```

---

## Task 3: `AppDialog.vue` — render `htmlBody`, honor `persistent`, scroll long content

**Files:**
- Modify: `frontend/app/components/AppDialog.vue`

- [ ] **Step 1: Branch the body rendering on `htmlBody`**

Open `frontend/app/components/AppDialog.vue`. Find the current body template:

```vue
<div class="dialog-text">
  <h3 v-if="state.title" id="dialog-title" class="dialog-title">{{ state.title }}</h3>
  <p class="dialog-message">{{ state.message }}</p>
</div>
```

Replace with a branched form:

```vue
<div class="dialog-text">
  <h3 v-if="state.title" id="dialog-title" class="dialog-title">{{ state.title }}</h3>
  <div
    v-if="state.htmlBody"
    class="dialog-markdown markdown-body"
    v-html="state.htmlBody"
  />
  <p v-else-if="state.message" class="dialog-message">{{ state.message }}</p>
</div>
```

The `markdown-body` class piggy-backs on any styles already present elsewhere in the app, and `dialog-markdown` adds dialog-specific overrides (defined in Step 4).

- [ ] **Step 2: Gate `onOverlayClick` and `onEsc` on `state.persistent`**

Find:

```ts
function onOverlayClick() {
  // Mirror native confirm: clicking outside is treated as cancel for confirm,
  // and as confirm for alert (since alert has only one action).
  if (state.value.mode === 'alert') ok()
  else cancel()
}
function onEsc() {
  if (state.value.mode === 'alert') ok()
  else cancel()
}
```

Replace with persistent-aware versions:

```ts
function onOverlayClick() {
  if (state.value.persistent) return
  // Mirror native confirm: clicking outside is treated as cancel for confirm,
  // and as confirm for alert (since alert has only one action).
  if (state.value.mode === 'alert') ok()
  else cancel()
}
function onEsc() {
  if (state.value.persistent) return
  if (state.value.mode === 'alert') ok()
  else cancel()
}
```

- [ ] **Step 3: Cap the dialog panel height for scrollable content**

Find the `.dialog-panel` style block:

```css
.dialog-panel {
  width: 100%;
  max-width: 440px;
  background-color: #ffffff;
  border-radius: 0.875rem;
  box-shadow: 0 20px 50px -10px rgba(15, 23, 42, 0.35), 0 8px 16px -8px rgba(15, 23, 42, 0.2);
  padding: 1.5rem 1.75rem 1.25rem;
  outline: none;
}
```

Add `max-height` + `display: flex` so the body region can scroll while the footer stays pinned:

```css
.dialog-panel {
  width: 100%;
  max-width: 520px;
  max-height: min(80vh, 720px);
  display: flex;
  flex-direction: column;
  background-color: #ffffff;
  border-radius: 0.875rem;
  box-shadow: 0 20px 50px -10px rgba(15, 23, 42, 0.35), 0 8px 16px -8px rgba(15, 23, 42, 0.2);
  padding: 1.5rem 1.75rem 1.25rem;
  outline: none;
}
```

Also widen the panel from `440px` to `520px` (above) so richer markdown bodies (images, code blocks) breathe a little. Then find `.dialog-body`:

```css
.dialog-body {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
}
```

Update so its content area can scroll without pushing the footer off-screen:

```css
.dialog-body {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
```

Find `.dialog-text`:

```css
.dialog-text {
  flex: 1;
  min-width: 0;
  padding-top: 0.125rem;
}
```

Make it scrollable:

```css
.dialog-text {
  flex: 1;
  min-width: 0;
  padding-top: 0.125rem;
  overflow-y: auto;
}
```

- [ ] **Step 4: Add `.dialog-markdown` scoped styles**

Append to the `<style scoped>` block (just before the closing `</style>`) the following rules. These mirror the typography conventions used elsewhere in the app for markdown content:

```css
.dialog-markdown {
  font-size: 0.875rem;
  line-height: 1.6;
  color: #1f2937;
}
:root.dark .dialog-markdown {
  color: #e5e7eb;
}
.dialog-markdown h1 {
  font-size: 1.15rem;
  font-weight: 700;
  margin: 0.5em 0 0.4em;
}
.dialog-markdown h2 {
  font-size: 1.05rem;
  font-weight: 600;
  margin: 0.6em 0 0.4em;
}
.dialog-markdown h3 {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0.6em 0 0.3em;
}
.dialog-markdown p {
  margin: 0.4em 0;
}
.dialog-markdown ul,
.dialog-markdown ol {
  margin: 0.4em 0;
  padding-left: 1.5em;
}
.dialog-markdown ul {
  list-style-type: disc;
}
.dialog-markdown ol {
  list-style-type: decimal;
}
.dialog-markdown li {
  margin: 0.2em 0;
}
.dialog-markdown strong {
  font-weight: 600;
}
.dialog-markdown em {
  font-style: italic;
}
.dialog-markdown code {
  background-color: rgba(15, 23, 42, 0.06);
  padding: 0.15em 0.35em;
  border-radius: 3px;
  font-size: 0.85em;
}
:root.dark .dialog-markdown code {
  background-color: rgba(255, 255, 255, 0.08);
}
.dialog-markdown pre {
  background-color: #f3f4f6;
  padding: 0.75rem 0.875rem;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.5em 0;
}
:root.dark .dialog-markdown pre {
  background-color: #1f2937;
}
.dialog-markdown pre code {
  background: none;
  padding: 0;
}
.dialog-markdown a {
  color: #6366f1;
  text-decoration: none;
}
.dialog-markdown a:hover {
  text-decoration: underline;
}
:root.dark .dialog-markdown a {
  color: #818cf8;
}
.dialog-markdown blockquote {
  border-left: 3px solid #d1d5db;
  padding-left: 0.875rem;
  color: #6b7280;
  margin: 0.5em 0;
}
:root.dark .dialog-markdown blockquote {
  border-left-color: #4b5563;
  color: #9ca3af;
}
.dialog-markdown img {
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  margin: 0.5em 0;
  display: block;
}
.dialog-markdown hr {
  border: none;
  border-top: 1px solid #e5e7eb;
  margin: 0.75em 0;
}
:root.dark .dialog-markdown hr {
  border-top-color: #374151;
}
```

- [ ] **Step 5: Type-check the frontend**

```bash
npx nuxi typecheck
```

Expected: no NEW errors traceable to AppDialog.vue.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/AppDialog.vue
git commit -m "feat(AppDialog): render htmlBody, support persistent, scroll long content"
```

---

## Task 4: New composable `useBroadcastPopup`

**Files:**
- Create: `frontend/app/composables/useBroadcastPopup.ts`

- [ ] **Step 1: Create the composable**

Create `frontend/app/composables/useBroadcastPopup.ts`:

```ts
import type { NotificationItem } from '~/composables/useNotifications'

interface BroadcastListResponse {
  count: number
  next: string | null
  previous: string | null
  results: NotificationItem[]
}

export function useBroadcastPopup() {
  const { api } = useApi()
  const { alert } = useDialog()
  const { markRead } = useNotifications()
  const { md } = useMentionMarkdown()
  // Single-fire guard, shared across the SSR/CSR boundary. Resets on full page reload.
  const started = useState<boolean>('broadcast_popup_started', () => false)

  async function start() {
    if (started.value) return
    started.value = true
    let res: BroadcastListResponse
    try {
      res = await api<BroadcastListResponse>(
        '/api/notifications/?notification_type=broadcast&is_read=false&page_size=20',
      )
    } catch {
      // Silent fail — bell still surfaces unread state.
      return
    }
    const queue = res.results || []
    for (const n of queue) {
      try {
        await alert({
          title: n.title,
          htmlBody: md.render(n.content || ''),
          persistent: true,
          confirmText: '知道了',
        })
      } catch {
        // If the dialog ever rejects, stop the queue — it's an unexpected state.
        return
      }
      try {
        await markRead(n.id)
      } catch {
        // Network or auth error on markRead — keep the queue going so other
        // broadcasts can still be seen and dismissed this session. The unread
        // one will pop again next time.
      }
    }
  }

  return { start }
}
```

- [ ] **Step 2: Type-check the frontend**

From `frontend/`:

```bash
npx nuxi typecheck
```

Expected: no NEW errors traceable to the new file. Nuxt auto-imports `useState`, `useApi`, `useDialog`, `useNotifications`, `useMentionMarkdown` — no explicit imports needed.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/composables/useBroadcastPopup.ts
git commit -m "feat(notifications): add useBroadcastPopup composable"
```

---

## Task 5: Wire the trigger in `layouts/default.vue`

**Files:**
- Modify: `frontend/app/layouts/default.vue`

- [ ] **Step 1: Wire `onMounted` to call `start()`**

Open `frontend/app/layouts/default.vue`. The current `<script setup>` block reads:

```ts
onErrorCaptured((err) => {
  console.error('[PAGE ERROR]', err)
  return false
})
```

Update it to also call the broadcast popup on mount:

```ts
onErrorCaptured((err) => {
  console.error('[PAGE ERROR]', err)
  return false
})

onMounted(() => {
  useBroadcastPopup().start()
})
```

`useBroadcastPopup` is auto-imported. The internal `useState` guard ensures the popup runs once per app load even if the layout remounts (e.g., HMR in dev). Since `default.vue` wraps every `/app/*` route, client-side navigation between issue, project, settings, etc. pages does not re-trigger the popup. `auth.vue` (login, register) uses a separate layout, so unauthenticated routes never call this.

- [ ] **Step 2: Type-check the frontend**

```bash
npx nuxi typecheck
```

Expected: no NEW errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/layouts/default.vue
git commit -m "feat(layout): trigger broadcast popup on /app/* entry"
```

---

## Task 6: Manual end-to-end verification

No automated frontend tests exist for this layout. Verify with a real browser session.

- [ ] **Step 1: Start the backend**

From `backend/`:

```bash
uv run python manage.py migrate
uv run python manage.py runserver
```

Expected: backend on `:8000`.

- [ ] **Step 2: Start the frontend**

From `frontend/`:

```bash
npm run dev
```

Expected: frontend on `:3004` (proxies `/api/**` to backend).

- [ ] **Step 3: Publish a test broadcast**

Log in as an admin user. Either go to `/app/notifications/manage/create` and create a notification with type `广播` and target `全员`, OR use curl:

```bash
TOKEN=<paste from localStorage.access_token>
curl -X POST http://localhost:3000/api/notifications/manage/create/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "测试广播弹窗",
    "content": "## 新功能\n\n这是一个**测试**广播\n\n- 列表项 1\n- 列表项 2",
    "notification_type": "broadcast",
    "target_type": "all",
    "is_draft": false
  }'
```

(If `notification_type` is not accepted in the create endpoint payload, check `apps/notifications/views.py` and `serializers.py` for the manage endpoint — broadcast type is set server-side on the existing broadcast endpoint. In that case, create through the admin UI or via Django shell.)

- [ ] **Step 4: Verify the popup appears**

Reload the app (`http://localhost:3000/app/home` or any `/app/*` route). The popup should appear with:
- The broadcast title at the top.
- The body rendered as Markdown (heading + paragraph + bullet list).
- A single `知道了` button.

Try clicking the dark overlay outside the dialog. The popup should NOT close. Press `Esc`. The popup should NOT close.

- [ ] **Step 5: Verify dismissal marks the broadcast read**

Click `知道了`. The popup closes. Open the browser network tab — confirm `POST /api/notifications/{id}/read/` fires and returns 200.

- [ ] **Step 6: Verify it does not re-fire**

Navigate to a different `/app/*` route (e.g. `/app/issues`). No popup.
Refresh the page. No popup (the broadcast is now read).

- [ ] **Step 7: Verify queue behavior with multiple broadcasts**

Create two broadcasts (e.g. "测试广播 A" and "测试广播 B"). Reload. The first popup appears (newest first — B), then on dismissal the second appears (A), then no more popups. Each dismissal fires its own `markRead` call.

- [ ] **Step 8: Verify non-broadcast notifications are unaffected**

Create a `mention` or `system` notification targeted at the same user. Reload. No popup. The notification only shows in the bell.

- [ ] **Step 9: Final commit (only if fixes were needed)**

If steps 4–8 surfaced bugs, fix them with small follow-up commits and re-verify. Otherwise no commit is needed at this step.

---

## Self-Review

**Spec coverage:**

| Spec requirement | Covered in |
|---|---|
| Backend `?notification_type=` filter | Task 1 |
| `useDialog.alert()` gains `htmlBody` | Task 2 (steps 1–3) |
| `useDialog.alert()` gains `persistent` | Task 2 (steps 1–4) + Task 3 (step 2) |
| `AppDialog.vue` renders `htmlBody` via `v-html` | Task 3 (step 1) |
| `AppDialog.vue` blocks backdrop/Esc when `persistent` | Task 3 (step 2) |
| Panel scrolls long content with `max-height` cap | Task 3 (step 3) |
| `.dialog-markdown` scoped styles | Task 3 (step 4) |
| `useBroadcastPopup` composable with single-fire guard | Task 4 |
| Newest-first iteration | Task 4 (API default order, no client-side reverse) |
| Per-iteration `markRead` catch so failures don't break queue | Task 4 |
| Trigger in `layouts/default.vue` `onMounted` | Task 5 |
| `auth.vue` (login/register) does not fire popup | Task 5 (architectural — auth.vue does not import `useBroadcastPopup`) |
| Manual verification of all the above | Task 6 |

**Placeholder scan:** No "TBD", "implement later", or unspecified error handling. Every code change shows the full surrounding context to be replaced.

**Type consistency:**
- `BroadcastListResponse` in Task 4 mirrors the existing `PaginatedResponse<NotificationItem>` shape from `useNotifications.ts` (`count`, `next`, `previous`, `results`).
- `NotificationItem` is imported by name from `~/composables/useNotifications`.
- `alert()` returns `Promise<void>` — Task 4's `await alert(...)` resolves to `undefined`, which the `for` loop tolerates.
- `markRead(id: string)` matches the signature in `useNotifications.ts`.
- `state.htmlBody` and `state.persistent` field names are identical in `useDialog.ts` (Task 2) and `AppDialog.vue` (Task 3).

**Scope:** Single feature, six tasks, six commits. No unrelated cleanups. Each task ships an independently-testable, revertable change.
