# apps/web — Aryx Next.js UI

**Isolated by design.** This app talks to the Aryx FastAPI over HTTP and nothing else. There is no shared code with the Python backend — only the wire-format JSON contract (REST + MCP). To rip this app out one day: `rm -rf apps/web/`, drop the `web` service from `docker-compose.yml`, point a new client at the same FastAPI.

## Stack

- Next.js 14 (app router) · React 18 · TypeScript
- Tailwind CSS 3 · Aryx brand tokens
- Framer Motion · Lucide icons
- Inter (body) · Fraunces (display) · JetBrains Mono

## Dev

```bash
cd apps/web
npm install
npm run dev    # http://localhost:3000
```

The app expects FastAPI at `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8088`).

## Docker

```bash
docker compose up -d web
# http://localhost:3000
```

## Brand

Palette + spacing live in `tailwind.config.ts` and `app/globals.css`. The logo is `public/aryx-logo.png` (a copy of `src/aryx/ui/assets/Aryx_logo.png` — owned by the web app's deploy unit, not symlinked).
