# Frontend Redesign — Multimodal RAG

> Instructions for the CLI agent. Read this whole file before touching code.
> The work is split into **Day 1 (foundation + core flows)** and **Day 2 (data-heavy pages + polish)**.
> Finish and commit each task before starting the next. Do NOT change backend API contracts.

---

## 0. Ground Rules (apply to every task)

1. **Inspect first.** Read `package.json`, the router, the existing pages (Login, Register, Documents, Query, Metrics, Evaluation) and the API client. List what you found in a short `docs/frontend_audit.md` before changing anything.
2. **Keep all functionality.** Every existing feature, route, API call, and state must still work after the redesign. This is a reskin + UX upgrade, not a rewrite of business logic.
3. **Reuse the existing stack.** If Tailwind / a component lib is already installed, use it. Only add the libraries listed in section 2 if they are missing.
4. **No generic "AI app" look.** Avoid the default purple-to-indigo gradient button, centered floating card on a gradient, and emoji-as-icons. Use the design system below.
5. **Commit after every task** with message `feat(ui): <task id> <short description>`.
6. **Every page must have** loading (skeleton), empty, and error states.
7. **Accessibility baseline:** visible focus rings, `aria-label` on icon-only buttons, color contrast AA, full keyboard navigation.
8. At the end of each day, run the build + lint + typecheck and fix everything before stopping. Write a short `docs/day{N}_summary.md` listing what was done and what is left.

---

## 1. Design Direction

The reference is a **dark, IDE/analytics-style workspace**: a slim icon rail on the left, a context top bar, split panes, dense-but-airy stat cards, ring/donut charts, segmented tabs, and a persistent bottom status bar with a primary pill action.

### 1.1 Layout concept
- **Left icon rail (72px)** replaces the top nav: Documents, Query, Metrics, Evaluation, then user/logout pinned at the bottom. Tooltip on hover, active item has an accent bar on its left edge.
- **Top bar:** page title + breadcrumb on the left, live status chips in the middle (backend health, active model), user avatar menu on the right.
- **Main area:** panel-based workspace. Cards, split panes, and tabs instead of long scrolling pages.
- **Bottom status bar (36px):** shows live pipeline status (indexed chunks, credits, last query latency, selected model). Primary action button lives on the right when relevant (e.g. "Ask").

### 1.2 Color tokens (define as CSS variables / Tailwind theme)

| Token | Value | Use |
|---|---|---|
| `--bg-base` | `#0B0F1A` | App background |
| `--bg-panel` | `#111726` | Cards / panels |
| `--bg-elevated` | `#172033` | Hover, inputs, modals |
| `--border` | `#1F2A44` | Panel borders (1px) |
| `--text-primary` | `#E6EAF5` | Main text |
| `--text-secondary` | `#8A94AD` | Labels, helper text |
| `--accent` | `#2DE2A6` | Primary actions, success, active nav |
| `--accent-2` | `#7C6CF0` | Secondary charts, links |
| `--warn` | `#FFB547` | Warnings, reranking stage |
| `--danger` | `#FF5C7A` | Errors, delete |
| `--info` | `#4CC9F0` | Info chips, retrieval stage |

Also add a subtle `--glow-accent: 0 0 24px rgba(45,226,166,.25)` used sparingly on primary buttons and active rings.

### 1.3 Typography
- UI font: **Inter** (variable). Headings: **Space Grotesk** or **Sora**.
- Mono (IDs, metrics, code, citations): **JetBrains Mono**.
- Scale: 12 / 13 / 14 / 16 / 20 / 28 / 40. Big metric numbers use mono + tabular-nums.

### 1.4 Shape, spacing, motion
- Radius: 10px panels, 8px inputs/buttons, 999px chips and pill CTAs.
- Spacing on a 4px grid. Panel padding 20px.
- Motion: 150ms ease-out for hovers, 250ms for panel/route transitions, spring for list items. Always respect `prefers-reduced-motion`.

---

## 2. Libraries (install only if missing)

| Purpose | Package |
|---|---|
| Icons (replace all emojis) | `lucide-react` |
| Animation | `framer-motion` |
| Charts (ring, bars, sparklines) | `recharts` |
| Toasts | `sonner` |
| Command palette | `cmdk` |
| Resizable split panes | `react-resizable-panels` |
| Markdown answers + code highlight | `react-markdown`, `remark-gfm`, `rehype-highlight` |
| Class helpers | `clsx`, `tailwind-merge` |

---

# DAY 1 — Foundation, Shell, Auth, Documents, Query

**Goal by end of day:** new design system in place, new app shell live, and the three user-facing flows (Auth, Documents, Query) fully redesigned and working.

### D1-T1 · Audit and setup (≈30 min)
- Create `docs/frontend_audit.md` (routes, components, API calls, state management, styling approach).
- Install missing libraries from section 2.
- Create a branch `feat/ui-redesign`.
- **Done when:** audit file exists, app still builds.

### D1-T2 · Design tokens and global styles (≈45 min)
- Implement all tokens from 1.2 as CSS variables and map them in the Tailwind theme (or equivalent).
- Load Inter, Space Grotesk/Sora, JetBrains Mono (self-host or `@fontsource`).
- Global styles: dark `color-scheme`, custom thin scrollbars, `::selection` using accent at 30% opacity, focus-ring utility, subtle background (very faint dot grid or noise at 3% opacity, no big gradients).
- **Done when:** a scratch page shows every token, font, and radius correctly.

### D1-T3 · UI primitives library (≈1.5 h)
Create `src/components/ui/` with typed, reusable components, each with variants and states:
- `Button` (primary with glow, secondary, ghost, danger, icon-only, loading spinner)
- `Input`, `Textarea`, `Select`, `PasswordInput` (show/hide toggle)
- `Card` / `Panel` (header, body, footer slots)
- `Badge` / `Chip` (success, warn, danger, info, neutral)
- `Tabs` (segmented control style like the reference's Today / Yesterday / This week)
- `Tooltip`, `Modal`/`Dialog`, `Skeleton`, `EmptyState`, `ProgressBar`, `Kbd` (keyboard hint)
- Wire `sonner` Toaster globally with themed styling.
- **Done when:** a `/dev/ui` route (dev-only) renders every primitive in every state.

### D1-T4 · App shell (≈1.5 h)
- Build `AppShell` with: left icon rail, top bar, main outlet, bottom status bar (see 1.1).
- Active route highlighting with an animated indicator (framer-motion `layoutId`).
- Page transition: fade + 8px upward slide between routes.
- Responsive: under 900px the rail collapses into a bottom tab bar; under 640px the status bar hides.
- Top bar chips: active model (read from Query page state/store), backend health (poll existing health endpoint if one exists; otherwise skip the chip).
- Status bar pulls stats already available from the API (document count, chunk count, last latency). If a value is unavailable, hide it rather than faking it.
- **Done when:** all four routes render inside the new shell with working navigation and logout.

### D1-T5 · Login and Register (≈1 h)
- Split layout: left side = brand panel with a subtle animated pipeline visual (Embedding → Retrieval → Reranking → LLM nodes with a traveling pulse, pure CSS/SVG); right side = form.
- Floating-label or clean-label inputs, inline validation, show/hide password, loading state on submit, clear error messages (no layout jump).
- Smooth switch between Sign In and Register (animated, no full reload).
- **Done when:** both forms work against the real API, validation and error states verified.

### D1-T6 · Documents page (≈2 h)
- **Upload zone:** large dropzone with animated dashed border on drag-over, file type chips (PDF, DOCX, PPTX, XLSX, PNG, JPG, WEBP), 50 MB limit shown, client-side validation with toast errors.
- **Upload/ingestion progress:** per-file card with a horizontal stepper showing pipeline stages (Upload → Parse → Chunk → Embed → Index) driven by real status from the API; if the API only exposes a coarse status, map it honestly and use an indeterminate bar for the rest.
- **Document list:** switch to a grid/list toggle. Each item shows file-type icon (color-coded per type), name (truncate with tooltip), size, chunk count (mono), credits used, document ID chip with click-to-copy, status badge (Processing / Complete / Failed).
- Row actions: **Query** (navigates to Query with that doc pre-selected), **Delete** (confirm dialog, optimistic removal with undo toast), **View Details** (slide-over drawer instead of inline expand).
- Search box + sort (newest, name, size) above the list. Skeleton rows while loading. Friendly empty state with an upload CTA.
- **Done when:** upload, list, query-handoff, delete, and details drawer all work.

### D1-T7 · Query page (≈2.5 h)
Redesign as a **two-pane workspace** using `react-resizable-panels`:
- **Left pane (conversation):**
  - Message thread (user bubbles + assistant answers) instead of a single answer block. Keep history in component state (and localStorage if sensible).
  - Composer pinned at the bottom: auto-growing textarea, `Ctrl+Enter` hint via `Kbd`, model selector as a compact dropdown with provider icon, document filter shown as removable chips above the composer, primary "Ask" pill button with loading state.
  - Streaming-feel UX: animated typing indicator, then render answer as Markdown (code highlighting, tables). If the API is not streaming, reveal the text with a fast typewriter effect that can be skipped by click.
  - Under each answer: latency chip, model chip, "Copy", "Regenerate", and thumbs up/down (log locally if no endpoint exists).
- **Right pane (evidence):** tabbed (Sources / Tables / Images / Trace)
  - Sources: citation cards with document name, page/chunk ID (mono), relevance score as a small ring or bar, text snippet with highlighted query terms.
  - Tables and Images: render retrieved tables as real HTML tables and images as a lightbox-enabled gallery.
  - Trace: per-stage timings for this query (Embedding, Retrieval, Reranking, LLM) as a mini stacked bar.
- Clicking an inline citation marker like `[1]` in the answer scrolls to and highlights the matching source card.
- Suggested prompt chips in the empty state (generic ones plus ones derived from the selected document name).
- **Done when:** a full ask → answer → sources → citation-click flow works with the real backend.

### D1-T8 · Day 1 wrap-up (≈30 min)
- Run build, lint, typecheck; fix everything.
- Smoke test: login → upload → query → logout.
- Write `docs/day1_summary.md`.

---

# DAY 2 — Metrics, Evaluation, Interactions, Polish

**Goal by end of day:** analytics-grade Metrics and Evaluation pages, global power-user features, polish, accessibility, performance, and QA.

### D2-T1 · Shared chart components (≈1 h)
Build in `src/components/charts/` (themed to the tokens, animated on mount):
- `StatCard` (icon, label, big mono value, delta/subtext, optional sparkline)
- `RingChart` (donut with center label, like the 50% / 45% / 5% donut in the reference)
- `StageBar` (horizontal bar with label, value, color)
- `StackedBar`, `Sparkline`, `ComparisonBars` (before vs after)
- Number count-up animation (800ms, ease-out, respects reduced motion).
- **Done when:** each component renders from mock props in `/dev/ui`.

### D2-T2 · Metrics dashboard (≈2.5 h)
Rebuild the Observability page as a dashboard grid:
- **Top row:** StatCards for Total Queries, Cache Hit Rate (as RingChart), Records Analysed, Avg End-to-End, P95 Latency. Include "Last refreshed" text with a live "auto-refresh in Ns" countdown and a manual Refresh button with spin state; keep the existing 30 s auto-refresh.
- **Time-range tabs** (segmented): Today / Yesterday / This week. If the API has no time filter, filter client-side from returned records; if records lack timestamps, hide the tabs and note it in the summary.
- **Latency panel:** per-stage breakdown (Embedding, Retrieval, Reranking, LLM, ADE) as StageBars with value labels, sorted by duration, plus a one-line insight generated from data (e.g. "ADE is 62% of total time"). Add a P95 vs average comparison.
- **Cost and usage panel:** Total LLM cost, Embedding cost, Total cost, Total tokens. Show costs with sensible precision (tooltip shows full value), provider breakdown as a RingChart (Groq / OpenRouter / NVIDIA) if data allows.
- **Recent queries table:** columns for time, question (truncated), model, latency, cache hit badge, cost. Row click opens a drawer with the full per-stage trace. Add column sort and a simple filter box.
- Loading skeletons for every card; graceful empty state ("No queries yet — ask your first question") with a link to Query.
- **Done when:** dashboard renders real data, auto-refresh works without flicker, drawer works.

### D2-T3 · Evaluation page (≈2 h)
- Header with K selector (1, 3, 5, 10) as segmented control and a **Run Evaluation** pill button with the accent glow.
- Running state: progress panel with animated stage text and per-question progress if the API provides it; otherwise an indeterminate bar and elapsed timer.
- Results:
  - Four hero StatCards: Recall@K before, Recall@K after, Precision@K before, Precision@K after, each with a colored delta badge (green up / red down).
  - `ComparisonBars` chart: before vs after reranking for Recall and Precision.
  - Per-question results table: question, expected source, rank before, rank after, hit/miss badges. Expandable rows show retrieved chunks.
  - Export results as JSON/CSV button.
- Persist the last result in localStorage so the page isn't empty after refresh, with a "last run at" timestamp.
- **Done when:** a run completes and renders all sections; error state shown if the run fails.

### D2-T4 · Global power features (≈1.5 h)
- **Command palette** (`Ctrl/Cmd+K`) with `cmdk`: navigate to pages, jump to a document, switch model, start a new query, logout.
- **Keyboard shortcuts:** `g d`, `g q`, `g m`, `g e` to navigate; `/` focuses the query box; `?` opens a shortcuts cheat sheet modal.
- **Notifications:** standardize all success/error feedback to `sonner` toasts with consistent copy.
- **Connection awareness:** banner when the backend is unreachable, with a retry button.
- **Session handling:** on 401 redirect to login with a toast and return-to path after re-login.

### D2-T5 · Micro-interactions and visual polish (≈1.5 h)
- Hover lift (translateY -2px + border brightens) on cards; press-scale on buttons.
- Staggered list entrance animations (30ms step) for documents, sources, table rows.
- Accent glow on focus for primary inputs; animated gradient hairline along the top of the active panel (subtle, 1px).
- Replace every remaining emoji or legacy icon with `lucide-react`.
- Custom 404 and error-boundary pages in the same style.
- Optional but nice: light theme toggle using the same token names (only if time remains; do not let it block anything else).

### D2-T6 · Responsive, accessibility, performance (≈1.5 h)
- Test at 1440, 1024, 768, 390 px widths; fix overflow and cramped layouts (tables scroll horizontally inside their panel, never the page).
- Keyboard-only pass on every page; fix focus order, trap focus in modals/drawers, return focus on close.
- Add `aria-live` to toasts and the answer region; label all icon buttons.
- Check contrast of `--text-secondary` on `--bg-panel` (AA); adjust token if needed.
- Performance: route-level code splitting (`lazy` + `Suspense` with skeleton fallback), lazy-load `recharts` and `react-markdown`, memoize heavy lists, avoid re-render of the whole shell on poll updates. Target Lighthouse Performance 90+ and Accessibility 95+ on the production build.

### D2-T7 · QA and handoff (≈1 h)
Run this checklist and fix failures:
- [ ] Login / Register / Logout, including wrong-password error
- [ ] Upload each file type, reject oversize/unsupported files
- [ ] Delete with undo, details drawer, copy document ID
- [ ] Query with and without document filter, each model option
- [ ] Citation click highlights the source; tables and images render
- [ ] Metrics auto-refresh, manual refresh, time tabs, drawer trace
- [ ] Evaluation run, results, export, persisted last result
- [ ] Command palette and all keyboard shortcuts
- [ ] Backend-down banner and 401 redirect
- [ ] No console errors or warnings; build, lint, typecheck all pass
- [ ] Reduced-motion mode disables non-essential animation

Then write `docs/day2_summary.md` and a final `docs/ui_redesign_notes.md` covering the design system, component inventory, shortcuts, and any API gaps you worked around.

---

## 3. Definition of Done

- The app is visually unrecognizable from the old one: dark workspace, icon rail, split panes, ring charts, and status bar, matching section 1.
- All original features work against the unchanged backend.
- Every page has skeleton, empty, and error states.
- Build, lint, and typecheck are clean; Lighthouse targets met.
- Summaries and notes docs are committed.

## 4. If You Run Short on Time

Cut in this order (last item first): light theme toggle, provider-cost ring chart, Trace tab details, thumbs up/down, export button, shortcut cheat sheet. Never cut: app shell, Query two-pane layout, Metrics dashboard, loading/empty/error states.