# CodeGuard AI — Frontend

React + TypeScript + Vite starter for the CodeGuard AI review workspace.

Requirements: Node.js 20+ and npm.

From this folder, run \`npm install\` then \`npm run dev\`. Open the local URL printed by Vite (normally http://127.0.0.1:5173).

The Vite development server proxies \`/api\` and \`/health\` to FastAPI on port 8000. If the API is not running, the UI uses clearly labelled local sample data.

Run \`npm run build\` to type-check and produce a production build.

The current dashboard includes sample findings, filters, search, and finding details. Its demo scan button is illustrative; live scanning is not implemented yet.