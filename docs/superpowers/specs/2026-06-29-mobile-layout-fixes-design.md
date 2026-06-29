# Mobile Layout Fixes — Design

Date: 2026-06-29
Branch context: `perf/issues-page-loading` (follow-up UI work)

## Problem

Four mobile-mode (`<768px`) layout defects reported with screenshots on the deployed app:

1. **Markdown editor toolbar overflows** — the `编辑 / 预览` tabs plus ~10 formatting buttons sit on one row and overflow horizontally on narrow screens.
2. **Notification dropdown goes off-screen** — the bell dropdown is fixed-width and anchored to the bell, so its left edge runs off the viewport.
3. **Bottom bar hides page content** — the fixed glass bottom nav covers the bottom of the scroll area, so the issue list pagination (`上一页 / 下一页`) is unreachable.
4. **Chat FAB overlaps the bottom bar** — the green global-messages floating button sits on top of the bottom bar's `更多` tab.

## Scope & Constraints

- All changes are gated to mobile (`<768px`) via Tailwind `max-md:` variants, the `useMobile()` composable, or `@media (max-width:767px)`. **Desktop (≥768px) behavior is unchanged.**
- No backend changes. No new dependencies.
- Follow existing patterns: Tailwind utility classes, `useState`-backed shared state in composables, the existing `_more` "command tab" handling in the bottom bar.

## Design

### Fix 1 — Toolbar wraps (chosen: wrap, not scroll/overflow-menu)

File: `frontend/app/components/MarkdownEditor.vue`

- The tab+toolbar container (`<div class="flex items-center border-b ...">`) gains `flex-wrap` so the toolbar group can drop to a second line on narrow widths.
- The toolbar group (`<div v-show="mode==='edit'" class="flex items-center gap-0.5 ml-auto pr-2">`) keeps `ml-auto` on `md:` (stays right-aligned on desktop), but on mobile the wrap lets it fall below the `编辑/预览` tabs and itself wrap across rows.
- Pure CSS/class change; no script changes. Buttons stay full-size and all remain visible.

### Fix 2 — Notification dropdown anchors to viewport on mobile

File: `frontend/app/components/NotificationBell.vue`

- Desktop unchanged: `absolute right-0 top-full mt-2 w-80`.
- Add `max-md:` overrides so the panel becomes viewport-anchored full-width with margins:
  `max-md:fixed max-md:left-2 max-md:right-2 max-md:top-16 max-md:w-auto max-md:mt-0`.
- `top-16` (4rem = 64px) places it just below the `h-16` header. Result: an always-on-screen panel with 8px side gutters.

### Fix 3 — Bottom padding clears the bar

File: `frontend/app/layouts/default.vue`

- `<main>` currently: `... p-3 md:p-6 lg:p-8 pb-20 md:pb-6 lg:pb-8`.
- The glass bar's real height = safe-area inset + `mb-3` (12px) + bar body (~58px), which exceeds the current `pb-20` (80px) on notched devices.
- Replace the mobile bottom padding with one that accounts for the bar + safe area:
  `pb-[calc(7rem+env(safe-area-inset-bottom))]` (≈112px + inset). `md:pb-6 lg:pb-8` stay as-is, so desktop is unchanged.

### Fix 4 — Global messages become a dedicated bottom-bar tab on mobile

Chosen interaction (confirmed with user):
- Tapping the `消息` tab **toggles** the chat panel open/closed.
- Tapping a real route tab (`问题跟踪` / `GitHub 仓库` / `仪表板`) or `更多` **closes** the chat panel, then performs its normal action.
- Tapping anywhere else on the page closes the panel (existing outside-click behavior).
- Desktop keeps the original green FAB; the `消息` tab and the mobile panel sizing only exist `<768px`.

Four coordinated changes:

**4a. Lift panel open state into the composable** — `frontend/app/composables/useChat.ts`
- Move `open` (and `view`) from `ChatBubble.vue` local refs into `useState`-backed state in `useChat()`:
  `const open = useState('chat-open', () => false)` and `const view = useState<'list'|'thread'>('chat-view', () => 'list')`.
- Export them plus a `toggleChat()` helper (`open.value = !open.value`).
- `ChatBubble.vue` consumes these from the composable instead of declaring its own refs; its `toggle()`/`back()`/click-outside logic is rewired to the shared refs (no behavior change on desktop).

**4b. Add the tab + badge wiring** — `frontend/app/components/AppBottomTabBar.vue`
- Insert before the `更多` item:
  `{ id: '_chat', label: '消息', icon: 'i-heroicons-chat-bubble-oval-left', badge: unreadTotal }` (pull `unreadTotal`, `toggleChat` from `useChat()`).
- In the `selectedTabId` setter:
  - `'_chat'` → call `toggleChat()`, then reset the slider selection back to the active route tab (same `resetting` pattern used for `'_more'`, so the thumb does not stick on `消息`).
  - `'_more'` and real-route taps → if chat `open`, set it closed first, then proceed (open the sheet / `router.push`).
- Add `data-mobile-tabbar` to the component's root container (used by 4d).

**4c. Badge support in the nav bar** — `frontend/app/components/liquid-glass/LiquidGlassBottomNavBar.vue`
- Extend `NavItem` with optional `badge?: number`.
- In the items layer, render a small red badge (dot or count) at the icon's top-right when `item.badge && item.badge > 0`, mirroring the existing FAB badge style. Purely additive; items without `badge` are unaffected.

**4d. Mobile panel sizing, hidden FAB, race-safe toggle** — `frontend/app/components/chat/ChatBubble.vue` (+ `ChatPreviewToast.vue`)
- `@media (max-width:767px)`:
  - `.chat-fab` → `display:none` (the tab is the entry point on mobile).
  - `.chat-panel` → full-width with gutters and seated above the bar: `left:12px; right:12px; width:auto; bottom:calc(86px + env(safe-area-inset-bottom)); height:min(584px, calc(100vh - 180px))`. (86px ≈ bar body 58px + `mb-3` 12px + ~16px gap; 180px leaves room for the header + bar.)
  - `.chat-toast` (in `ChatPreviewToast.vue`) → same gutter treatment and raised `bottom` so it clears the bar.
- **Race-safe toggle:** the `消息` tap fires on `mousedown`/`touchstart` inside the bottom bar, which would otherwise trip `ChatBubble`'s document click-outside handler and immediately re-close the panel. Guard it: in `onClickOutside`, skip when `e.composedPath()` contains an element matching `[data-mobile-tabbar]` (reusing the existing `composedPath` approach). This makes the explicit `toggleChat()` the sole open/close authority for taps originating in the bar, while page-content taps still close it.

**4e. Touch/compat-mouse de-duplication** — `frontend/app/components/liquid-glass/LiquidGlassBottomNavBar.vue`
- Found during verification: `handleItemClick` is bound to BOTH `@touchstart.passive` and `@mousedown`. On a real touch tap the browser fires `touchstart` and then a synthesized compatibility `mousedown`, so the handler runs **twice** per tap. The pre-existing `更多` tab survives this because its action is idempotent (`moreOpen = true` twice), but the new `消息` tab does a **toggle** (`open→close`), producing a visible flash-then-vanish.
- Fix at the source (single consumer = `AppBottomTabBar`): pass `$event` to `handleItemClick` and, after a `touchstart`, swallow the following `mousedown` for ~700ms (`suppressMouse` flag). One tap → one activation. Desktop (mouse-only) is unaffected since `touchstart` never fires there.

## Affected Files

- `frontend/app/components/MarkdownEditor.vue` — toolbar wrap classes
- `frontend/app/components/NotificationBell.vue` — `max-md:` dropdown anchoring
- `frontend/app/layouts/default.vue` — `<main>` mobile bottom padding
- `frontend/app/composables/useChat.ts` — lift `open`/`view` to `useState`, add `toggleChat`
- `frontend/app/components/AppBottomTabBar.vue` — `_chat` tab, setter logic, `data-mobile-tabbar`
- `frontend/app/components/liquid-glass/LiquidGlassBottomNavBar.vue` — `badge` support
- `frontend/app/components/chat/ChatBubble.vue` — consume shared state, mobile panel CSS, hide FAB, click-outside guard
- `frontend/app/components/chat/ChatPreviewToast.vue` — mobile toast positioning

## Verification

Manual, via `/browse` at mobile width (~390px) on a logged-in account (`bot` / `password123`):

1. Issue detail editor: toolbar wraps cleanly, no horizontal overflow; all buttons reachable.
2. Notification bell: dropdown opens fully on-screen below the header, both edges within the viewport.
3. Issue list: scroll to bottom — pagination `上一页 / 下一页` is fully visible above the bottom bar.
4. Bottom bar shows a `消息` tab with an unread badge when unread > 0; tapping it opens a full-width panel above the bar; tapping it again closes it; tapping a route tab closes the panel and navigates; the green FAB is absent on mobile.
5. Desktop (≥768px) regression check: FAB present and unchanged, no `消息` tab, notification dropdown and editor toolbar unchanged.

## Out of Scope

- Desktop redesign of any of these surfaces.
- Reworking the AppFooter behind the bottom bar (separate concern, not reported).
- Backend / WebSocket changes.
