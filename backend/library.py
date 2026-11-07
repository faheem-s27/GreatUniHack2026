"""A student's own slide library: the PDFs they add in "My Modules".

Staff upload official course slides through /api/lectures/{id}/pdf (staff
login). Students add their own lecture PDFs here so the coach can read them:

  POST /api/library/lectures?student_id=...&module_id=...&module_name=...&title=...[&assessed=true]
       body: the raw PDF (Content-Type: application/pdf)
       -> {lecture_id, course_id, slide_count, slides_with_text, assessed}
  GET  /api/library/lectures/{lecture_id}?student_id=...   status of one uploaded lecture

Each browser module becomes a private course "lib-<module id>" owned by the
student who created it: nobody else can add slides to it. Every upload is a
new lecture with its own id, so the coach searches one lecture at a time and
two lectures never see each other's slides.

assessed=true marks the PDF as assessed coursework: the coach stays in LOCKED
mode (hints only) for every question about it. That flag is stored on the
server when the PDF is uploaded; the coach never takes it from the browser
afterwards.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from db import connect
from events import log_event
from ingest import MAX_PDF_BYTES, ingest_pdf

router = APIRouter(prefix="/api/library", tags=["student library"])

ID = r"^[A-Za-z0-9_-]{1,64}$"


def is_assessed_lecture(conn, lecture_id: str) -> bool:
    row = conn.execute("SELECT assessed FROM library_lectures WHERE lecture_id = ?", (lecture_id,)).fetchone()
    return bool(row and row["assessed"])


@router.post("/lectures", status_code=201)
async def upload_lecture(
    request: Request,
    student_id: str = Query(min_length=1, max_length=64),
    module_id: str = Query(pattern=ID),
    module_name: str = Query(min_length=1, max_length=200),
    title: str = Query(min_length=1, max_length=200),
    assessed: bool = False,
):
    data = await request.body()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF is larger than 40 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(422, "Body must be a PDF file (Content-Type: application/pdf)")
    course_id = f"lib-{module_id}"
    lecture_id = f"lib-{uuid.uuid4().hex[:20]}"
    now = datetime.now(timezone.utc).isoformat()

    def work() -> dict:
        with connect() as conn:
            owner = conn.execute("SELECT student_id FROM library_courses WHERE course_id = ?", (course_id,)).fetchone()
            if owner is None:
                if conn.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone():
                    raise HTTPException(409, "This module id is already used")
                conn.execute("INSERT INTO courses (id, title, created_at) VALUES (?, ?, ?)", (course_id, module_name.strip(), now))
                conn.execute("INSERT INTO library_courses (course_id, student_id) VALUES (?, ?)", (course_id, student_id))
            elif owner["student_id"] != student_id:
                raise HTTPException(403, "This module belongs to another student")
            conn.execute(
                "INSERT INTO lectures (id, course_id, title, created_at) VALUES (?, ?, ?, ?)",
                (lecture_id, course_id, title.strip(), now),
            )
            conn.execute(
                "INSERT INTO library_lectures (lecture_id, student_id, assessed, created_at) VALUES (?, ?, ?, ?)",
                (lecture_id, student_id, int(assessed), now),
            )
            count = ingest_pdf(conn, lecture_id, data)
            with_text = conn.execute(
                "SELECT COUNT(*) FROM slides WHERE lecture_id = ? AND (body != '' OR title IS NOT NULL)", (lecture_id,)
            ).fetchone()[0]
            log_event(conn, "library_upload", student_id, course_id, lecture_id, ref_id=lecture_id,
                      slides=count, with_text=with_text, assessed=assessed)
            return {"lecture_id": lecture_id, "course_id": course_id, "slide_count": count,
                    "slides_with_text": with_text, "assessed": assessed}

    return await run_in_threadpool(work)


@router.get("/lectures/{lecture_id}")
def lecture_status(lecture_id: str, student_id: str = Query(min_length=1, max_length=64)):
    with connect() as conn:
        row = conn.execute(
            """SELECT ll.assessed, l.title, l.course_id, COUNT(s.id) AS slides,
                      SUM(s.body != '' OR s.title IS NOT NULL) AS with_text
               FROM library_lectures ll JOIN lectures l ON l.id = ll.lecture_id
               LEFT JOIN slides s ON s.lecture_id = l.id
               WHERE ll.lecture_id = ? AND ll.student_id = ? GROUP BY l.id""",
            (lecture_id, student_id),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Lecture not found")
    return {"lecture_id": lecture_id, "course_id": row["course_id"], "title": row["title"],
            "slide_count": row["slides"], "slides_with_text": row["with_text"] or 0, "assessed": bool(row["assessed"])}
