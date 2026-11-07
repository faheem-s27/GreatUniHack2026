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

## Deploy

One Docker image serves the API, the WebSockets and the built frontend on port 8000, with the database in a `/data` volume:

```sh
cp .env.example .env      # set LOSTPOINT_STAFF_CODE
docker compose up --build
```

All settings are environment variables, listed in `backend/config.py` and `.env.example`. `GET /api/health` checks the database and is used as the container health check. Every error response has the same shape, `{"detail": "...", "status": 404}`. Validation errors add `errors: [{field, message}]`.

## Useful commands

From `frontend`, run `npm run build` to check the production build and `npm run lint` to run ESLint.
