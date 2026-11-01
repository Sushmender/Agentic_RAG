# Multimodal RAG Frontend

Single-page React application for the Multimodal RAG platform. Built with React 19, Vite, Tailwind CSS, Framer Motion, and Lucide React.

For overall architecture, system design, and complete setup instructions, see the root [README.md](../README.md).

## Scripts

Run commands from the `frontend/` directory:

| Command | Description |
|---|---|
| `npm run dev` | Start the Vite local development server on `http://localhost:5173` |
| `npm run build` | Build production assets into the `dist/` directory |
| `npm run lint` | Run Oxlint fast static code analysis across source files |
| `npm run preview` | Locally preview the production build output |

## Environment Variables

Configuration is loaded from `frontend/.env` (see `frontend/.env.example`):

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000/api/v1` | Base URL for the backend REST API |

## Source Structure

```
frontend/src/
├── assets/          # Static logos and image assets
├── components/      # Modular React UI components
│   ├── charts/      # Recharts latency and cost visualization components
│   ├── chat/        # Chat tab strip, message history, input bar, citation chips
│   ├── layout/      # Top navigation, command palette, shortcuts modal, user menu
│   ├── ui/          # Accessible modal dialogs, status badges, buttons, tooltips
│   ├── ErrorBoundary.jsx  # React boundary for unhandled component exceptions
│   └── PageEvidence.jsx   # PDF/image page viewer with bounding-box highlights
├── context/         # React Context state providers (AuthContext, ChatContext)
├── hooks/           # Custom React hooks (keyboard shortcuts, tab management)
├── pages/           # Route views
│   ├── auth/        # Authentication pages (LoginPage, RegisterPage)
│   ├── DocumentsPage.jsx   # Document upload, listing, status tracking, deletion
│   ├── QueryPage.jsx       # Multi-tab RAG chat, citation inspector, trace details
│   ├── MetricsPage.jsx     # Telemetry dashboard, latency percentiles, stage charts
│   ├── EvaluationPage.jsx  # Recall@K and Precision@K benchmarking interface
│   └── DevUI.jsx           # Local-only component testing sandbox
├── services/        # HTTP API client layer (Axios instance, JWT interceptors)
└── utils/           # Utility helpers (formatting, token math, bbox coordinates)
```
