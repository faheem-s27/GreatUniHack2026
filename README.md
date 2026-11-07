## All Izz Well team

- Faheem
- Jamie
- Stephanie
- Nevia
- JC

# LostPoint

A lecture companion foundation for the GreatUniHack project brief. The repository contains a React + Vite + Tailwind frontend and a FastAPI backend starter.

## Run locally

In one terminal:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

In another terminal:

```sh
cd frontend
npm install
npm run dev
```

Open the Vite URL printed in the terminal. The backend health endpoint is at `http://127.0.0.1:8000/api/health`, and API documentation is at `/docs`. Vite proxies `/api` requests to the backend during development.

## Current foundation

- A responsive demo lecture, slide navigation, and an “I'm lost” button. Saved moments are stored in the browser's local storage and can be marked understood.
- A demo coach with preset responses and a lecturer insights preview with sample data.
- A FastAPI backend with Canvas OAuth login, a SQLite-backed session store, and endpoints for enrolled courses, modules, and proxied PDF slides.
- A one-command local Canvas LMS setup (`./scripts/setup-canvas.sh`) that also provisions the OAuth developer key, demo student, and backend `.env`.

The sample lecture and dashboard are illustrative. Slide uploads/search, AI coaching and guardrails, accounts, SQLite/Chroma persistence, captions, translation, and real anonymised heatmaps still need to be implemented. The frontend demo does not currently communicate with the backend. Do not use the sample dashboard for real student data; enforce the five-student threshold on the server when implementing real insights.

## Canvas slides backend

The backend lets a student sign in with their Canvas account and read the PDF
slides attached to each course module:

```sh
./scripts/setup-canvas.sh          # Canvas + OAuth key + demo student + backend/.env
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload
```

With the Vite dev server running, visit
`http://localhost:5173/api/auth/canvas/login` and sign in as
`student@lostpoint.local` / `lostpoint-student`. Vite proxies the callback to
the backend.

To run the backend without the frontend, set
`CANVAS_REDIRECT_URI=http://localhost:8000/api/auth/canvas/callback` in
`backend/.env` and visit `http://127.0.0.1:8000/api/auth/canvas/login` instead.
Both redirect URIs are registered on the developer key.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Service health |
| `GET` | `/api/auth/canvas/login` | Start Canvas OAuth |
| `GET` | `/api/auth/canvas/callback` | OAuth callback |
| `GET` | `/api/auth/me` | Current Canvas user |
| `POST` | `/api/auth/logout` | End the session |
| `GET` | `/api/courses` | Active enrolled courses |
| `GET` | `/api/courses/{id}/modules` | Modules with PDF slides |
| `GET` | `/api/files/{id}/content` | Proxied PDF for iframe rendering |

The Canvas access token stays server-side in SQLite; the browser only receives a
signed, HttpOnly session cookie. See [docs/canvas-local.md](docs/canvas-local.md)
for the full setup and troubleshooting guide.

## Local Canvas LMS

The Canvas integration is developed against a self-hosted, open-source Canvas
instance. See [docs/canvas-local.md](docs/canvas-local.md) and run
`./scripts/setup-canvas.sh` to bootstrap it.

## Useful commands

From `frontend`, run `npm run build` to check the production build and `npm run lint` to run ESLint.
