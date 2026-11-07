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

- A responsive demo lecture, slide navigation, a demo coach with preset responses.
- **"I'm lost" button (working end to end).** One tap saves the slide, topic and seconds into the lecture to the backend (SQLite). After the tap the student can optionally add a photo of the slide (downscaled to ≤1280px JPEG in the browser before upload). Double taps on the same slide within 30 s merge into one moment. If the backend is unreachable the moment is saved on the device and synced later, with no duplicates.
- **Lost moments page** shows the student's own moments with photo thumbnails; "Mark understood" is saved to the server.
- **Lecture insights** reads the live heatmap: distinct students lost per slide, with slides under 5 students hidden by the server. Falls back to sample data if the backend is down.

### Lost-moment API (`backend/lost_moments.py`)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/lost-moments` | Save a moment `{student_id, lecture_id, slide_number, topic?, lecture_time_s?, id?}` |
| GET | `/api/lost-moments?student_id=` | A student's own moments |
| PATCH | `/api/lost-moments/{id}` | `{student_id, resolved}` |
| PUT / GET | `/api/lost-moments/{id}/screenshot` | Attach / fetch the slide photo (base64 data URL in, image out) |
| GET | `/api/lectures/{lecture_id}/heatmap` | Anonymised per-slide counts (min 5 students) |

There are no accounts yet: `student_id` is a random id kept in the browser. Treat it as a placeholder until auth exists, because anyone who knows an id can read that student's moments.

For the demo, `cd backend && python seed_demo.py` adds 61 anonymous moments to the sample lecture so the heatmap has data (`--clear` removes them). Run the backend tests with `pip install pytest httpx && pytest`.

Still to do: slide uploads/search, AI coaching and guardrails, accounts, Chroma, captions and translation.

## Useful commands

From `frontend`, run `npm run build` to check the production build and `npm run lint` to run ESLint.
