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

## The coach on your own slides

1. Copy `backend/.env.example` to `backend/.env` and set `ANTHROPIC_API_KEY`. With no key, start the backend with `LOSTPOINT_COACH_PROVIDER=fake` to use Stephanie's scripted offline coach. Its replies are labelled "Offline demo coach".
2. In **My Modules**, upload a lecture PDF. It shows "✓ Coach can read it" once the server has read its text. Tick "assessed coursework" for coursework PDFs, so the coach only gives hints.
3. Open the lecture, go to a page and press **I'm lost**. Ask the coach a question. It searches only that lecture's slides, cites real slide numbers (click a citation to open that page), and switches between Guide, Explain and Hints only on the server.

`POST /api/coach` and `POST /api/library/lectures` are described in `backend/coach_api.py` and `backend/library.py`. The demo lecture uses the server's built-in demo slides.

## Current foundation

- A responsive demo lecture, slide navigation, a demo coach with preset responses.
- **"I'm lost" button (working end to end).** One tap saves the slide, topic and seconds into the lecture to the backend (SQLite). After the tap the student can optionally add a photo of the slide (downscaled to ≤1280px JPEG in the browser before upload). Double taps on the same slide within 30 s merge into one moment. If the backend is unreachable the moment is saved on the device and synced later, with no duplicates.
- **Lost moments page** shows the student's own moments with photo thumbnails; "Mark understood" is saved to the server.
- **Lecture insights** reads the live heatmap: distinct students lost per slide, with slides under 5 students hidden by the server. Falls back to sample data if the backend is down.

- A responsive demo lecture, slide navigation, and an “I'm lost” button. Saved moments are stored in the browser's local storage and can be marked understood.
- A demo coach with preset responses and a lecturer insights preview with sample data.
- A FastAPI backend with Canvas OAuth login, a SQLite-backed session store, and endpoints for enrolled courses, modules, and proxied PDF slides.
- A one-command local Canvas LMS setup (`./scripts/setup-canvas.sh`) that also provisions the OAuth developer key, demo student, and backend `.env`.

### Lost-moment API (`backend/lost_moments.py`)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/lost-moments` | Save a moment `{student_id, lecture_id, slide_number, topic?, lecture_time_s?, id?}` |
| GET | `/api/lost-moments?student_id=` | A student's own moments |
| PATCH | `/api/lost-moments/{id}` | `{student_id, resolved}` |
| PUT / GET | `/api/lost-moments/{id}/screenshot` | Attach / fetch the slide photo (base64 data URL in, image out) |
| GET | `/api/lectures/{lecture_id}/heatmap` | Anonymised per-slide counts (min 5 students) |

### Database and API for the other parts

All data is in one SQLite file, `backend/lostpoint.db` (schema and table list in `backend/db.py`). Existing databases gain new tables on the next start. Full request/response shapes are at `/docs`.

**Courses and slides** (`courses.py`), for the coursework dashboard and the coach's citations:

| Method | Path | Purpose |
| --- | --- | --- |
| GET / POST | `/api/courses` | List courses / create or update `{id, title, code?, term?}` |
| GET | `/api/courses/{course_id}` | Course with its lectures (week, slide count) |
| POST | `/api/courses/{course_id}/lectures` | Create or update a lecture `{id, title, week?, held_at?}` |
| GET | `/api/lectures/{lecture_id}` | Lecture with all its slide text |
| PUT | `/api/lectures/{lecture_id}/slides` | Replace slide text `{slides: [{slide_number, title?, topic?, body}]}` |
| GET | `/api/lectures/{lecture_id}/slides/{n}` | One slide, with a `citation` like "Week 3, slide 2" |
| PUT / GET | `/api/lectures/{lecture_id}/slides/{n}/image` | Attach / fetch a slide image |
| GET | `/api/search?q=&course_id=&lecture_id=` | Best-matching slides with citations (SQLite full-text search until Chroma) |

**Assessed coursework** (`coursework.py`): `GET/POST /api/courses/{course_id}/coursework`, `DELETE /api/coursework/{id}`, and `POST /api/coursework/check {course_id, text}` → `{locked, matches}`. Keywords should be specific to the assignment, not general topic words.

**Student memory** (`memory.py`): a gap is one idea one student struggles with. `POST /api/gaps {student_id, course_id, concept, lecture_id?, slide_number?, lost_moment_id?, root_gap_id?}` creates it or updates the existing one for that concept (and reopens it). `GET /api/gaps?student_id=`, `GET /api/gaps/{id}?student_id=` (with its lost moments and the `trace` of root gaps back to earlier weeks), `PATCH /api/gaps/{id}` to close/reopen or set the root.

**Coach storage** (`coach_store.py`): stores conversations and decides the mode in code. Explain unlocks after 3 student messages sent with `is_attempt: true`. Locked is set when the question or any later student message matches coursework, and never unlocks. Coach citations must point at real slides.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/coach/sessions` | Start `{student_id, course_id, question?, lost_moment_id?, lecture_id?, slide_number?, concept?}` |
| GET | `/api/coach/sessions/{id}/context?student_id=` | Everything the coach needs: the slide, related slides, open gaps, trace |
| POST | `/api/coach/sessions/{id}/messages` | `{student_id, role: student/coach, content, is_attempt?, citations?}`; returns the message and the updated mode |
| GET | `/api/coach/sessions?student_id=` and `/api/coach/sessions/{id}?student_id=` | List / read with messages |
| PATCH | `/api/coach/sessions/{id}` | `{student_id, status: "resolved"}` closes the gap and marks the lost moment understood |

Only honest attempts count towards explain mode: "idk", "?", one word or "just give me the answer" sent with `is_attempt` is stored but not counted (`guardrails.is_honest_attempt`).

**Slide upload from PDF** (`ingest.py`): `POST /api/lectures/{lecture_id}/pdf` with the raw PDF as the body (`Content-Type: application/pdf`) turns each page into a slide. Repeated footers, symbol-font bullets, ligatures and wrapped headings are cleaned up. To load a module before a demo:

```sh
cd backend
python ingest.py path/to/LectureNotes_Week1.pdf --course comp63301 --course-title "Data Engineering Concepts" --lecture de-w1 --week 1 --title "Week 1"
python ingest.py path/to/Coursework.pdf --course comp63301 --coursework de-cw3 --title "Coursework 3" --keywords "journey_solution" "cw3"
```

Search ignores filler words ("what is", "how does … work") and matches British and American spellings.

**Semantic search with Chroma (optional)** (`search_index.py`): keyword search always runs. To also find slides that explain an idea in different words, run `pip install chromadb`, set `LOSTPOINT_SEARCH=chroma` and run `python search_index.py reindex` once; new and uploaded slides are then indexed automatically. Results from both searches are merged, and each result says how it matched (`"match": "keyword" | "meaning" | "both"`). The embedding model runs locally (about 80 MB, downloaded on first use). If Chroma is missing or fails, search falls back to keywords.

**Live lecture** (`live.py`): one WebSocket room per lecture at `/ws/lectures/{lecture_id}?role=lecturer` or `?role=student&student_id=…` (Vite proxies `/ws`). The lecturer sends `start`, `slide` and `caption` messages. Captions are relayed and never stored. Students send `lost` to tap on the room's current slide, using the same dedupe as the REST route. Lecturers receive live `lost_count` per slide, hidden under 5 students. Attendance is stored, so the heatmap can show `percent_of_room`. Full message list in the module docstring; `GET /api/lectures/{id}/live` shows the room state.

**Heatmap and insights**: the heatmap also returns slide `title`/`topic`, `attendance`, `percent_of_room` and `most_lost_slide`, and the existing fields are unchanged. `GET /api/courses/{id}/insights` covers the whole course: each lecture's most-lost slide, the most-lost slides overall, and the concepts 5+ students have gaps on.

**Tutor handoff** (`handoffs.py`, human in the loop): when a student is lost on the same idea 3 times, or makes 6 honest attempts without closing it, a handoff opens automatically, and the coach message response says so in `handoff`. Students can also ask: `POST /api/handoffs {student_id, course_id, gap_id?, session_id?, note?, share_transcript?}`. Tutors use `GET /api/courses/{id}/handoffs` (queue) and `PATCH /api/handoffs/{id} {status: claimed|resolved, tutor, note}`. Students see replies at `GET /api/handoffs?student_id=`. The coach transcript is shared only if the student ticked `share_transcript`.

**Event log and metrics** (`events.py`, `insights.py`): every step is logged (taps, gap changes, coach sessions, attempts, mode changes with the reason, handoffs, recaps). `GET /api/events?student_id=` is a student's own timeline. `GET /api/courses/{id}/metrics` gives the brief's "How we know it works" numbers: repeat-lost rate (overall and by week), gaps that came back after coaching, coach resolution rate and attempts, handoffs, and slides the lecturer recapped (`POST /api/lectures/{id}/slides/{n}/recap`).

The coach's Python code can also import the helpers directly: `courses.search_slides`, `courses.get_slide`, `coursework.check_question`, `memory.record_gap`, `memory.open_gaps`, `memory.trace`.

### Accounts (`backend/accounts.py`)

`POST /api/auth/register {email, name, password, role?, staff_code?}`, `POST /api/auth/login {email, password}` (both return `{token, user}`), `POST /api/auth/logout`, `GET /api/auth/me`. Send `Authorization: Bearer <token>`. On the lecturer side of the live lecture socket, pass it as `?token=`.

- **Staff only** (lecturer or tutor login): creating courses, lectures and slides, PDF upload, the coursework list, course insights and metrics, recaps, the tutor queue and handoff updates, and the lecturer side of the live lecture.
- **No login needed**: everything a student does, plus reading courses, slides, search and the anonymised heatmap, so the current frontend works unchanged. Anonymous students still use a random `student_id` from the browser. Binding `student_id` to a logged-in student is the next step.
- **Creating staff accounts**: registering as a lecturer or tutor needs `LOSTPOINT_STAFF_CODE`. Without it, create staff on the server with `python accounts.py create-staff --email you@uni.ac.uk --name "Dr X" --role lecturer`.
- **How credentials are stored**: passwords are hashed with scrypt, and only a hash of each login token is stored. Five failed logins within 15 minutes lock that email out for the rest of the window.

For the demo, `cd backend && python seed_demo.py` adds the Calculus 1 course (`calc101`: week 2 and week 3 lectures with slide text, plus one assessed coursework) and 61 anonymous moments to the sample lecture so the heatmap has data (`--clear` removes the moments). It is safe to run again. Run the backend tests with `pip install -r requirements-dev.txt && pytest`.

Still to do: the AI coach itself, captions and translation (other team members), and binding student ids to student logins.

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

## Deploy

One Docker image serves the API, the WebSockets and the built frontend on port 8000, with the database in a `/data` volume:

```sh
cp .env.example .env      # set LOSTPOINT_STAFF_CODE
docker compose up --build
```

All settings are environment variables, listed in `backend/config.py` and `.env.example`. `GET /api/health` checks the database and is used as the container health check. Every error response has the same shape, `{"detail": "...", "status": 404}`. Validation errors add `errors: [{field, message}]`.

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
| `GET` | `/api/auth/canvas/me` | Current Canvas user |
| `POST` | `/api/auth/canvas/logout` | End the session |
| `GET` | `/api/canvas/courses` | Active enrolled courses |
| `GET` | `/api/canvas/courses/{id}/modules` | Modules with PDF slides |
| `GET` | `/api/canvas/files/{id}/content` | Proxied PDF for iframe rendering |

The Canvas access token stays server-side in SQLite; the browser only receives a
signed, HttpOnly session cookie. See [docs/canvas-local.md](docs/canvas-local.md)
for the full setup and troubleshooting guide.

## Local Canvas LMS

The Canvas integration is developed against a self-hosted, open-source Canvas
instance. See [docs/canvas-local.md](docs/canvas-local.md) and run
`./scripts/setup-canvas.sh` to bootstrap it.

## Useful commands

From `frontend`, run `npm run build` to check the production build and `npm run lint` to run ESLint.
