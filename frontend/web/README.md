# frontend/web

**Status:** runnable shell

This React application is the future supported TrialScribe browser client. It currently
renders only a platform-ready shell; routing, API access, authentication, uploads, and
protocol authoring are deferred to later features.

Use Node.js 24.18.0 and npm 11.16.0, then run from this directory:

```bash
npm ci
npm run dev
npm run lint
npm test
npm run build
```

The development server listens on `http://localhost:5173` by default.
