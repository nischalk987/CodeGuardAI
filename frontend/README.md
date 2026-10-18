# CodeGuard AI — Frontend

React + TypeScript + Vite starter for the CodeGuard AI review workspace.

Requirements: Node.js 20+ and npm.

From this folder, run \`npm install\` then \`npm run dev\`. Open the local URL printed by Vite (normally http://127.0.0.1:5173).

The Vite development server proxies \`/api\` and \`/health\` to FastAPI on port 8000. If the API is not running, the UI uses clearly labelled local sample data.

Run \`npm run build\` to type-check and produce a production build.

The dashboard includes severity and category filters, search across finding text and line context, severity summaries that follow the visible filters, and finding details with local accept/ignore triage. Findings are illustrative sample data whether loaded from FastAPI or the local fallback. “Preview demo” does not run analysis; live scanning is not implemented.

Run the unit tests with `npm test` and create a production build with `npm run build`.
