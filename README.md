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
- A FastAPI application with a health endpoint, ready for the team to extend.

The sample lecture and dashboard are illustrative. Slide uploads/search, AI coaching and guardrails, accounts, SQLite/Chroma persistence, captions, translation, and real anonymised heatmaps still need to be implemented. The frontend demo does not currently communicate with the backend. Do not use the sample dashboard for real student data; enforce the five-student threshold on the server when implementing real insights.

## Useful commands

From `frontend`, run `npm run build` to check the production build and `npm run lint` to run ESLint.
