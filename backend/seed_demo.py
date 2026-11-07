"""Fill the database with a demo course and anonymous lost moments.

Adds the Calculus 1 course with two lectures (week 2 and the week 3 lecture the
frontend shows, "calc-w3"), their slide text, one piece of assessed coursework,
and 61 anonymous lost moments so the heatmap has data. The heatmap hides
slides with fewer than 5 students, so a single demo tap is never visible on
its own.

Run once before the demo:  python seed_demo.py
Safe to run again: it replaces the demo data and leaves real data alone.
Seeded students have ids starting with "demo-"; --clear removes them (the
course and slides stay, since other features rely on them).
"""

import json
import random
import sys
import uuid
from datetime import datetime, timezone

from db import connect, init_db

COURSE = {"id": "calc101", "code": "MATH10101", "title": "Calculus 1", "term": "2026/27 Semester 1"}

LECTURES = [
    {
        "id": "calc-w2", "week": 2, "title": "Rates of change",
        "slides": [
            (1, "Why rates of change?", "Rates of change", "How fast does one quantity change when another one does?"),
            (2, "The derivative", "Derivatives", "The derivative f'(x) is the instantaneous rate of change of f at x: the slope of the tangent line."),
            (3, "Limit definition", "Derivatives", "f'(x) is the limit as h goes to 0 of (f(x + h) - f(x)) / h."),
            (4, "Power rule", "Differentiation rules", "For f(x) = x^n the derivative is n x^(n-1). So the derivative of x^2 is 2x."),
            (5, "Constants", "Differentiation rules", "The derivative of a constant is 0, because a constant does not change."),
            (6, "Sum rule", "Differentiation rules", "Differentiate a sum term by term: (f + g)' = f' + g'."),
            (7, "Product rule", "Differentiation rules", "(fg)' = f'g + fg'."),
            (8, "Chain rule", "Differentiation rules", "For f(g(x)) the derivative is f'(g(x)) g'(x)."),
            (9, "Treating things as constant", "Constants", "If c is a constant then the derivative of c x^2 is 2c x: the constant just comes along for the ride. This idea comes back in partial derivatives."),
        ],
    },
    {
        "id": "calc-w3", "week": 3, "title": "Introduction to Calculus: Multivariable functions",
        # Matches the slides hard-coded in frontend/src/App.jsx.
        "slides": [
            (1, "The big picture", "Functions of several variables", "What happens when an output depends on more than one input?"),
            (2, "Meet partial derivatives", "Partial derivatives", "A partial derivative describes how a function changes as one variable changes, while the others stay constant. f(x, y) = x^2 + y^2"),
            (3, "A closer look", "Holding variables constant", "To find the partial derivative with respect to x, treat y as a constant."),
        ],
    },
]

COURSEWORK = [
    {
        "id": "calc101-cw1", "title": "Coursework 1: Partial derivatives",
        "description": "Find both partial derivatives of g(x, y) = x^2 y + sin(xy) and evaluate them at (1, pi).",
        "keywords": ["x^2 y + sin(xy)", "x^2y + sin(xy)", "coursework 1", "cw1"],
        "due_at": "2026-11-20",
    },
]

LECTURE_ID = "calc-w3"
# slide number -> how many seeded students got lost there
DEMO_COUNTS = {1: 3, 2: 41, 3: 17}


def seed_course(conn, now: str) -> None:
    conn.execute(
        """INSERT INTO courses (id, code, title, term, created_at) VALUES (:id, :code, :title, :term, :now)
           ON CONFLICT(id) DO UPDATE SET code = excluded.code, title = excluded.title, term = excluded.term""",
        {**COURSE, "now": now},
    )
    for lecture in LECTURES:
        conn.execute(
            """INSERT INTO lectures (id, course_id, week, title, created_at) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET week = excluded.week, title = excluded.title""",
            (lecture["id"], COURSE["id"], lecture["week"], lecture["title"], now),
        )
        conn.executemany(
            """INSERT INTO slides (lecture_id, slide_number, title, topic, body) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(lecture_id, slide_number) DO UPDATE SET title = excluded.title, topic = excluded.topic, body = excluded.body""",
            [(lecture["id"], *slide) for slide in lecture["slides"]],
        )
    for cw in COURSEWORK:
        conn.execute(
            """INSERT INTO coursework (id, course_id, title, description, keywords, due_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET title = excluded.title, description = excluded.description,
                   keywords = excluded.keywords, due_at = excluded.due_at""",
            (cw["id"], COURSE["id"], cw["title"], cw["description"], json.dumps(cw["keywords"]), cw["due_at"], now),
        )


def main() -> None:
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        seed_course(conn, now)
        conn.execute("DELETE FROM lost_moments WHERE student_id LIKE 'demo-%'")
        if "--clear" in sys.argv:
            print("Removed seeded demo moments.")
            return
        for slide, count in DEMO_COUNTS.items():
            for i in range(count):
                conn.execute(
                    """INSERT INTO lost_moments (id, student_id, lecture_id, slide_number, lecture_time_s, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4()), f"demo-{slide}-{i}", LECTURE_ID, slide, random.randint(slide * 600, slide * 600 + 300), now),
                )
    slides = sum(len(l["slides"]) for l in LECTURES)
    print(f"Seeded course {COURSE['id']} ({len(LECTURES)} lectures, {slides} slides, {len(COURSEWORK)} coursework)"
          f" and {sum(DEMO_COUNTS.values())} demo moments for {LECTURE_ID}.")


if __name__ == "__main__":
    main()
