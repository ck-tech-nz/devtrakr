# Markdown Link Hover Preview — Design

Date: 2026-06-15
Status: Approved (design), pending implementation plan

## Summary

Add a hover-triggered preview popup for links rendered inside markdown content
(issue descriptions, comments, AI-analysis output). When the user rests the
mouse over a previewable link for a short delay, a floating card appears:

- **Internal issue references** (`#问题-290`, rendered as `a.mention-issue`) →
  a compact issue card (title + number, status + priority, assignee + time).
- **External URLs** (`a[href^=http]` to a different host) → a live `<iframe>`
  embed of the page, with graceful degradation when the site refuses framing.

The feature is delivered as a **reusable, editor-agnostic component** so any
surface that renders markdown can opt in, and so new link types (users,
projects, external OG cards) can be added later as pluggable resolvers.

## Goals

- One shared hover-preview mechanism reused across all markdown render surfaces.
- Internal issue reference preview that reuses existing issue API + color config.
- External URL live preview using a pure-frontend iframe (no backend this phase).
- Extensible architecture: adding a new link type = registering a new resolver.

## Non-Goals (this phase)

- No backend OG/unfurl service for external URLs (browser CORS forces a backend
  proxy for metadata cards; explicitly deferred). External preview is iframe-only.
- No touch/long-press support — desktop hover only.
- No mandatory migration of the existing `.md` file-attachment hover preview;
  the architecture leaves room to fold it in as a third resolver later.

## Background: why this shape

- DevTrakr frontend is a **browser SPA**. A cross-origin `fetch` of an external
  page's HTML is blocked by CORS, so a metadata/OG card would require a backend
  proxy. A cross-origin `<iframe src>` is *navigation*, not a scripted read, so
  it is allowed without a backend — this is the chosen approach for external URLs.
- The hard limitation: many sites send `X-Frame-Options: DENY/SAMEORIGIN` or CSP
  `frame-ancestors`, and the browser refuses to render them in an iframe. Unlike
  an Electron app (e.g. Obsidian), a browser SPA cannot strip these response
  headers. We therefore design for graceful degradation, not for universal embed.
- The codebase already contains a manual hover-preview pattern for `.md` file
  attachments (`MarkdownEditor.vue` `.md-hover-preview`: Teleport to body, 500ms
  delay, auto flip above/below). This design generalizes that pattern.

## Existing code touchpoints (verified)

- Markdown renderer (singleton `markdown-it`): `frontend/app/composables/useMentionMarkdown.ts`
  - `mentionPlugin()` renders issue refs: regex `^#\[([^\]]+)\]\(issue:(\d+)\)`
    → `<a href="/app/issues/${id}" class="mention-issue">` (~lines 116–136)
  - `fileCardPlugin()` adds `target="_blank" rel="noopener noreferrer"` to links
    (~lines 36–94)
- Rendered output via `v-html` in:
  - `frontend/app/components/MarkdownView.vue`
  - `frontend/app/components/MarkdownEditor.vue` (preview tab)
  - `frontend/app/pages/app/issues/[id].vue` (AI analysis result)
- Existing hover pattern to generalize: `MarkdownEditor.vue` `.md-hover-preview`
  (Teleport, `getBoundingClientRect` positioning, 500ms delay, flip logic).
- Single issue API: `GET /api/issues/{id}/` →
  `backend/apps/issues/serializers.py` `IssueDetailSerializer` (~219–271).
  Returns: `id`, `title`, `status`, `priority`, `assignee_name`,
  `assignee_avatar`, `created_by_name`, `created_at`, `updated_at`, …
- Color/label config: `frontend/app/composables/usePriority.ts`,
  `frontend/app/composables/useStatus.ts` (label + background color helpers).
- Conventions: `<script setup lang="ts">`, scoped CSS + Tailwind, dark mode via
  `:root.dark`.

## Architecture

### Chosen approach: composable + single teleported card + resolver registry

`useLinkHoverPreview(containerRef)` attaches a delegated `mouseover` listener to
a rendered-markdown container. On hover of an `<a>`, it asks each registered
**resolver** whether it matches; the first match drives a single shared
`LinkHoverCard.vue` (teleported to `<body>`).

Rejected alternatives:
- **Nuxt UI `UPopover`/`UTooltip` per link** — links live inside `v-html`; you
  cannot mount Vue component instances into that output, and one popover per link
  is awkward and heavy.
- **markdown-it plugin wrapping each link in a custom web component** — works but
  adds build/runtime complexity disproportionate to the benefit.

### Units

1. **`useLinkHoverPreview(containerRef)`** (composable)
   - Delegated `mouseover`/`mouseleave` on the container.
   - On hover: `target.closest('a')` → run resolver registry → if matched, start
     `setTimeout(HOVER_DELAY = 500ms)` → show card.
   - Lifecycle: keep open while pointer is inside the card (`mouseenter` cancels
     teardown); destroy 300ms after pointer leaves both link and card.
   - Positioning: reuse the `.md-hover-preview` logic — Teleport to body,
     `getBoundingClientRect`, flip above/below on insufficient viewport space.
   - Returns nothing the caller must manage beyond passing the container ref;
     auto-cleans listeners on unmount.

2. **Resolver registry** (`{ match(anchor): boolean, type: string, ...data }`)
   - Built-in: `issue`, `external`. Designed so additional resolvers (user,
     project, external-OG) register without touching the shell.

3. **`LinkHoverCard.vue`** (teleported shell)
   - Renders branch by resolver type. Shared frame: positioning, sizing
     (default max 600×400, viewport-clamped), enter/leave handlers, dark mode.

4. **Issue resolver**
   - Match: `a.mention-issue`. Add `data-issue-id="{id}"` in `mentionPlugin`
     renderer for a clean id read (instead of parsing the href).
   - Data: `GET /api/issues/{id}/`, behind an in-memory cache keyed by id (no
     duplicate fetch); skeleton while loading; error state on failure.
   - Card: title + `#问题-{id}`; status pill + priority pill via
     `useStatus`/`usePriority` colors; assignee (avatar + name) + created/updated
     time. Whole card click → navigate `/app/issues/{id}`.

5. **External resolver**
   - Match: `a[href^="http"]` with host ≠ current host. Add an `external-link`
     class in the renderer for robust matching.
   - Content: live `<iframe>` with a loading state.
   - Security: `sandbox="allow-scripts allow-same-origin allow-popups"`
     (deliberately **no** `allow-top-navigation` so an embedded page cannot
     hijack the top tab); `referrerpolicy="no-referrer"`.
   - Degradation: blocked sites (X-Frame-Options/CSP) typically render blank and
     do not fire `onerror`. Strategy: if `onload` does not report success within
     ~3s, fall back to a compact card showing domain + favicon + "Open in new
     tab". A URL bar with an open button is always present at the top of the card
     so blocked links still expose useful info and an escape hatch.

### Integration points

- `MarkdownView.vue`, `MarkdownEditor.vue` (preview tab), and
  `issues/[id].vue` (AI result) each pass their render container ref to
  `useLinkHoverPreview`.
- Renderer change in `useMentionMarkdown.ts`: add `data-issue-id` to issue-ref
  anchors and `external-link` class to external anchors.

## Edge cases

- Touch devices (no hover): feature disabled this phase.
- Rapid mouse movement / nested hovers: reuse existing timeout-based teardown to
  avoid popup flicker / stacking.
- Same-host links (internal app routes that are not issue refs): not previewed.
- Dark mode: card styles mirror `:root.dark`, matching existing chip styling.

## Testing

- Resolver matching: `issue` vs `external` vs no-match anchors.
- Issue card: correct fields rendered; color pills from settings; cache hit
  avoids a second fetch.
- Interaction: hover delay fires; pointer-into-card keeps it open; leave tears
  down; iframe load-timeout triggers fallback card.

## Open questions

None blocking. Future: backend OG unfurl card for external links; user/project
resolvers; touch long-press; migrating the `.md` file hover into this shell.
