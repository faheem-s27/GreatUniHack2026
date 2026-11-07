"""Read lecture slides from a PDF into the slides table (one PDF page = one slide).

API
  POST /api/lectures/{lecture_id}/pdf      body: the raw PDF bytes (Content-Type: application/pdf)
                                           replaces the lecture's slide text, returns the lecture

Command line, for loading a module's slides before a demo:
  python ingest.py --course comp63301 --course-title "Data Engineering" \\
                   --lecture de-w1 --week 1 --title "Week 1: Concepts" path/to/LectureNotes_Week1.pdf
  python ingest.py --course comp63301 --coursework de-cw3 --title "Coursework 3" \\
                   --keywords "journey time" "pvr" path/to/Coursework_3.pdf

Each page's text is cleaned (page numbers, repeated headers/footers and
hyphenated line breaks removed). The first short line becomes the slide title.
Pages with no text (pictures only) are kept as empty slides so slide numbers
still match the PDF the student sees.
"""

import argparse
import io
import json
import logging
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from courses import SlideIn, get_lecture, write_slides
from accounts import require_staff
from db import connect, init_db

router = APIRouter(prefix="/api", tags=["slide ingest"])

# pypdf logs a warning for every slightly malformed object; real decks have hundreds.
logging.getLogger("pypdf").setLevel(logging.ERROR)

MAX_PDF_BYTES = 40 * 1024 * 1024
MAX_PAGES = 400
MAX_BODY_CHARS = 20_000
TITLE_MAX_CHARS = 120


def read_pdf_pages(data: bytes) -> list[str]:
    from pypdf import PdfReader  # imported here so the API starts even without pypdf
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            reader.decrypt("")
        pages = reader.pages
        if len(pages) > MAX_PAGES:
            raise HTTPException(413, f"PDF has more than {MAX_PAGES} pages")
        return [page.extract_text() or "" for page in pages]
    except (PdfReadError, ValueError, KeyError) as e:
        raise HTTPException(422, f"Could not read this PDF: {e}") from None


# Bullet glyphs from symbol fonts usually come out as U+FFFD or private-use characters.
BULLETS = re.compile(r"^[�•▪◦●➢]+\s*")


def _clean_lines(text: str) -> list[str]:
    # NFKC turns ligatures into plain letters ("satisﬁable" -> "satisfiable") so search finds them.
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join hyphenated words
    lines = []
    for line in text.splitlines():
        line = " ".join(line.split())
        line = BULLETS.sub("• ", line).replace("�", "")
        if line and line != "•" and not re.fullmatch(r"(page\s*)?\d+(\s*(/|of)\s*\d+)?", line, re.I):
            lines.append(line)
    return lines


def _footer_key(line: str) -> str:
    # "Sandra Sampaio 12" and "Sandra Sampaio 13" are the same footer.
    return re.sub(r"\d+", "#", line).strip()


def pages_to_slides(pages: list[str]) -> list[SlideIn]:
    page_lines = [_clean_lines(p) for p in pages]
    # A line that appears on most pages (course code, lecturer name, page
    # footer) is a header or footer, not content.
    counts = Counter(key for lines in page_lines for key in {_footer_key(line) for line in lines})
    repeated = {key for key, n in counts.items() if len(pages) >= 4 and n >= 0.6 * len(pages)}

    slides = []
    for number, lines in enumerate(page_lines, start=1):
        lines = [line for line in lines if _footer_key(line) not in repeated]
        title, body_lines = _split_title(lines)
        slides.append(SlideIn(
            slide_number=number,
            title=title,
            body="\n".join(body_lines)[:MAX_BODY_CHARS],
        ))
    return slides


def _split_title(lines: list[str]) -> tuple[str | None, list[str]]:
    """The slide title is the first line, if it looks like a heading.

    A bullet point is not a title. A heading wrapped over two short lines
    ("What is the Data" / "Lifecycle?") is joined back together.
    """
    if not lines or lines[0].startswith("•") or len(lines[0]) > TITLE_MAX_CHARS:
        return None, lines
    title, rest = lines[0], lines[1:]
    if (
        rest
        and not title.endswith((".", ":", "?", "!"))
        and len(rest[0].split()) <= 2  # "Lifecycle?" yes; "Takes time & effort" no
        and not rest[0][-1].isdigit()  # "Sandra Sampaio 2" is a footer, not a title
        and not rest[0].startswith(("•", "-", "–", "o "))
        and len(title.split()) <= 6
    ):
        title, rest = f"{title} {rest[0]}", rest[1:]
    return title, rest


def ingest_pdf(conn, lecture_id: str, data: bytes) -> int:
    """Replace a lecture's slides with the pages of a PDF. Returns the slide count."""
    slides = pages_to_slides(read_pdf_pages(data))
    write_slides(conn, lecture_id, slides)
    return len(slides)


@router.post("/lectures/{lecture_id}/pdf", dependencies=[Depends(require_staff)])
async def upload_pdf(lecture_id: str, request: Request):
    data = await request.body()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF is larger than 40 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(422, "Body must be a PDF file (Content-Type: application/pdf)")
    def work() -> int:
        with connect() as conn:
            return ingest_pdf(conn, lecture_id, data)

    # Text extraction is CPU-bound and can take a while on big decks; keep it
    # off the event loop so live lectures are not blocked meanwhile.
    count = await run_in_threadpool(work)
    return {**get_lecture(lecture_id), "ingested_pages": count}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("pdf")
    p.add_argument("--course", required=True, help="course id, e.g. comp63301")
    p.add_argument("--course-title", help="creates the course if it does not exist")
    p.add_argument("--code")
    p.add_argument("--lecture", help="lecture id to load slides into")
    p.add_argument("--week", type=int)
    p.add_argument("--title", help="lecture or coursework title")
    p.add_argument("--coursework", help="store this PDF as assessed coursework with this id instead")
    p.add_argument("--keywords", nargs="*", default=[], help="coursework phrases that lock the coach")
    args = p.parse_args(argv)
    if bool(args.lecture) == bool(args.coursework):
        p.error("give exactly one of --lecture or --coursework")

    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with open(args.pdf, "rb") as f:
        data = f.read()
    with connect() as conn:
        if conn.execute("SELECT 1 FROM courses WHERE id = ?", (args.course,)).fetchone() is None:
            if not args.course_title:
                p.error(f"course {args.course} does not exist; pass --course-title to create it")
            conn.execute(
                "INSERT INTO courses (id, code, title, created_at) VALUES (?, ?, ?, ?)",
                (args.course, args.code, args.course_title, now),
            )
        if args.coursework:
            text = "\n\n".join(" ".join(page.split()) for page in read_pdf_pages(data))
            conn.execute(
                """INSERT INTO coursework (id, course_id, title, description, keywords, created_at) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET title = excluded.title, description = excluded.description, keywords = excluded.keywords""",
                (args.coursework, args.course, args.title or args.coursework, text[:5000], json.dumps(args.keywords), now),
            )
            print(f"Stored coursework {args.coursework} ({len(args.keywords)} keywords).")
            return
        conn.execute(
            """INSERT INTO lectures (id, course_id, week, title, created_at) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET week = COALESCE(excluded.week, week), title = excluded.title""",
            (args.lecture, args.course, args.week, args.title or args.lecture, now),
        )
        count = ingest_pdf(conn, args.lecture, data)
        empty = conn.execute(
            "SELECT COUNT(*) FROM slides WHERE lecture_id = ? AND body = '' AND title IS NULL", (args.lecture,)
        ).fetchone()[0]
    print(f"Loaded {count} slides into {args.lecture}" + (f" ({empty} with no text, e.g. pictures)" if empty else "") + ".")


if __name__ == "__main__":
    try:
        main()
    except HTTPException as e:
        sys.exit(f"Error: {e.detail}")
