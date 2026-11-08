---
paths:
  - "frontend/src/**"
---
# Frontend rules
- JSX function components; pages in `src/pages/` (PascalCase); routes only in `src/App.js`; nav in `src/components/Layout.jsx`. Add role gates there, but remember the backend is the real authorization.
- All HTTP goes through `src/lib/api.js` wrappers (Axios, token interceptor). `lib/api.js` and `context/AuthContext.js` are the session boundary: change only with explicit approval.
- `src/components/ui/` is generated shadcn-style code; do not edit it for feature work.
- State is local `useState`/`useEffect`; no query cache is installed. Notify with Sonner.
- Keep vocabulary explicit: lowercase local enums. Animal tag fields on events are plain comma-separated text inputs.
- `REACT_APP_BACKEND_URL` is baked in at build time (see frontend/Dockerfile, cloudbuild.yaml).
- No frontend tests exist. Validate with `npm run build` (includes ESLint); mention any manual UI check you could not do.
