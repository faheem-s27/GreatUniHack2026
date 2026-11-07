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

The coach's Python code can also import the helpers directly: `courses.search_slides`, `courses.get_slide`, `coursework.check_question`, `memory.record_gap`, `memory.open_gaps`, `memory.trace`.

There are no accounts yet: `student_id` is a random id kept in the browser. Treat it as a placeholder until auth exists, because anyone who knows an id can read that student's moments.

For the demo, `cd backend && python seed_demo.py` adds the Calculus 1 course (`calc101`: week 2 and week 3 lectures with slide text, plus one assessed coursework) and 61 anonymous moments to the sample lecture so the heatmap has data (`--clear` removes the moments). It is safe to run again. Run the backend tests with `pip install pytest httpx && pytest`.

Still to do: slide upload (reading PDFs into slide text), the AI coach itself, accounts, Chroma, captions and translation. Lecturer routes (courses, slides, coursework) are open to anyone until accounts exist.

## Useful commands

From `frontend`, run `npm run build` to check the production build and `npm run lint` to run ESLint.
