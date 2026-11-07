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
- A demo coach UI backed by the Claude tutoring engine, plus a lecturer insights preview with sample data.
- A FastAPI application with health and coach endpoints and a separate terminal-first AI coach.

The sample lecture and dashboard are illustrative. Slide uploads/search, accounts, SQLite/Chroma persistence, captions, translation, and real anonymised heatmaps still need to be implemented. The browser coach uses a server-owned copy of the demo slides (1–3), not uploaded slides. Do not use the sample dashboard for real student data; enforce the five-student threshold on the server when implementing real insights.

## Browser coach trial

Set `ANTHROPIC_API_KEY` in `backend/.env` and, if needed, set `ANTHROPIC_MODEL` to a model available to your account. Start both servers using the commands above, open the Vite URL, then select **My coach** and send a question. The browser sends messages to `POST /api/coach` through Vite's `/api` proxy. The backend returns a slide-citing reply, mode, wrong-attempt count and gap status. Each turn may make several paid API calls; the key stays in the backend and is never sent to the browser.

The browser creates a temporary session ID for this page load; the backend keeps its session state in memory until it restarts. Reloading resets the visible chat and starts a new session. This demo does not identify real students or assess real coursework: only server-owned slide data controls the coach's assessed flag. Replace the demo slide source, session identity and in-memory store when the team's slide upload and accounts are ready. Replies are checked before display, so they are not streamed.

## Terminal coach

From `backend`, install dependencies with `pip install -r requirements.txt`. Put your Anthropic key in `backend/.env` as `ANTHROPIC_API_KEY=your_key_here` (this file is ignored by Git), then run:

```sh
python coach.py
```

The default model is `claude-sonnet-4-5`; optionally set `ANTHROPIC_MODEL` in `.env` to a model available to your account. Real use makes several paid API calls per turn. Type `/quit` to exit.

For an offline demo, run `python coach.py --fake`. Ask for help, then try three distinct messages beginning with `I think`, such as `I think all variables change`. In the fake provider, `I think other variables stay constant` is treated as a correct attempt. This provider is deliberately scripted and does not assess arbitrary answers. Use `python coach.py --fake --assessed` to demonstrate that assessed material stays locked. Omit `--fake` to use Anthropic, and add `--assessed` to lock the example topic.

The terminal demo's partial-derivatives slide, topic and in-memory session are placeholders. `demo_search(lecture_id, question)` returns `Slide` objects with numbers, text and an `assessed` flag; `MemoryStore.get/save` scopes state by student, lecture and concept. Replace these with the team's search and persistence implementations, and provide a trusted concept and assessment metadata from the backend. The terminal session is lost on exit. Assessed flags remain locked within a session; in a real integration the backend must reliably identify all assessed topics, rather than relying only on whichever slides search retrieves.

Mode selection and slide-number citation checks are enforced in code. Attempt judgment and the additional answer-leak review use separate model calls; both can be wrong and do not guarantee that a solution can never leak. Failed response checks retry twice, then return a fixed fallback. Replies are fully generated and checked before display; no unchecked tokens are streamed. A gap is marked closed only after the attempt judge accepts a correct answer, although that judgment also requires real-world evaluation.

Run offline tests with `python -m unittest test_coach test_main` from `backend`.

## Useful commands

From `frontend`, run `npm run build` to check the production build and `npm run lint` to run ESLint.
