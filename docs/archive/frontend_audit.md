# Frontend Audit — Multimodal RAG
_Generated: 2026-10-16 during D1-T1_

---

## Routes

| Path | Component | Protected |
|---|---|---|
| `/login` | `LoginPage` | No (redirects → `/` if authed) |
| `/register` | `RegisterPage` | No (redirects → `/` if authed) |
| `/` | `DocumentsPage` | Yes |
| `/query` | `QueryPage` | Yes |
| `/metrics` | `MetricsPage` | Yes |
| `/evaluation` | `EvaluationPage` | Yes |
| `*` | Redirects → `/` | — |

---

## Components Inventory

| Component | File | Description |
|---|---|---|
| `Navbar` | `components/layout/Navbar.jsx` | Top nav with links + logout. Uses emoji icons. |
| `DocumentsPage` | `pages/DocumentsPage.jsx` | Upload zone, doc list, status polling |
| `QueryPage` | `pages/QueryPage.jsx` | Query form, answer box, source cards, telemetry |
| `MetricsPage` | `pages/MetricsPage.jsx` | Observability dashboard, auto-refresh 30s |
| `EvaluationPage` | `pages/EvaluationPage.jsx` | RAG eval run with K selector |
| `LoginPage` | `pages/LoginPage.jsx` | Login form |
| `RegisterPage` | `pages/RegisterPage.jsx` | Register form |

### Sub-components (inline in pages)
- `StatusBadge`, `DocumentCard`, `DocCardSkeleton`, `ErrorBanner`, `UploadZone` (DocumentsPage)
- `RouteTag`, `ModelBadge`, `AnswerBox`, `BBoxGrounding`, `SourceCard`, `TelemetryPanel`, `DebugPanel`, `QuerySkeleton` (QueryPage)
- `MetricCard`, `LatencyBar` (MetricsPage)
- `ImprovementBadge`, `EvalSkeleton`, `AggregateCards`, `PerQuestionTable` (EvaluationPage)

---

## API Calls

| Method | Endpoint | Used In |
|---|---|---|
| POST | `/auth/register` | RegisterPage |
| POST | `/auth/login` | LoginPage |
| POST | `/documents/upload` | DocumentsPage |
| GET | `/documents/` | DocumentsPage, QueryPage |
| GET | `/documents/{id}` | DocumentsPage (polling) |
| DELETE | `/documents/{id}` | DocumentsPage |
| GET | `/jobs/{id}` | DocumentsPage (status polling) |
| POST | `/query` | QueryPage |
| GET | `/health` | api.js (defined, not used in UI yet) |
| GET | `/metrics` | MetricsPage |
| GET | `/evaluation/run?k=N` | EvaluationPage |

---

## State Management

- **Auth state**: `AuthContext` (React Context) — user, token stored in `localStorage`.
- **Per-page local state**: `useState`/`useEffect` only — no global store (Zustand/Redux).
- **Polling**: `setInterval` in refs inside DocumentsPage for job status.
- **Toast notifications**: `sonner` already integrated.

---

## Styling Approach

- **Framework**: Vanilla CSS (no Tailwind, no CSS modules).
- **Per-page CSS files**: `AuthPage.css`, `DocumentsPage.css`, `QueryPage.css`, `MetricsPage.css`, `EvaluationPage.css`, `Navbar.css`.
- **Global**: `index.css` with CSS custom properties.
- **Current theme**: Dark purple/indigo gradient (`#0a0a1a` bg, `#6366f1` primary) — will be replaced.
- **Fonts**: Only Inter loaded from Google Fonts. No mono or heading font yet.
- **Icons**: Emoji only — to be replaced with `lucide-react`.

---

## Missing Libraries (to install)

| Package | Status |
|---|---|
| `lucide-react` | ❌ Missing |
| `framer-motion` | ❌ Missing |
| `recharts` | ❌ Missing |
| `cmdk` | ❌ Missing |
| `react-resizable-panels` | ❌ Missing |
| `rehype-highlight` | ❌ Missing |
| `clsx` | ❌ Missing |
| `tailwind-merge` | ❌ Missing |
| `@fontsource/inter` | ❌ Missing (using CDN) |
| `@fontsource/space-grotesk` | ❌ Missing |
| `@fontsource/jetbrains-mono` | ❌ Missing |
| `react-markdown` | ✅ Already installed |
| `remark-gfm` | ✅ Already installed |
| `sonner` | ✅ Already installed |
| `react-dropzone` | ✅ Already installed |

---

## Known Issues / Notes

1. `Navbar` uses emoji icons — will be replaced with `lucide-react`.
2. No skeleton states on MetricsPage auto-refresh (flickers).
3. No keyboard navigation in document selector chips.
4. QueryPage has no conversation history — single answer replaces previous.
5. No bottom status bar, no icon rail — currently a top navbar.
6. Auth pages are centered cards on gradient — will be redesigned per spec.
7. No `prefers-reduced-motion` support currently.
8. `window.confirm` used for delete confirmation — will be replaced with a Dialog.
9. `healthAPI.check()` defined but not polled in UI yet.
