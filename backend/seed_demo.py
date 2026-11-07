"""Fill the demo lecture with anonymous lost moments so the heatmap has data.

The heatmap hides slides with fewer than 5 students, so a single demo tap is
never visible on its own. Run once before the demo:  python seed_demo.py
Seeded students have ids starting with "demo-" and can be removed with --clear.
"""

import random
import sys
import uuid
from datetime import datetime, timezone

from db import connect, init_db

LECTURE_ID = "calc-w3"
# slide number -> how many seeded students got lost there
DEMO_COUNTS = {1: 3, 2: 41, 3: 17}


def main() -> None:
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM lost_moments WHERE student_id LIKE 'demo-%'")
        if "--clear" in sys.argv:
            print("Removed seeded demo moments.")
            return
        now = datetime.now(timezone.utc).isoformat()
        for slide, count in DEMO_COUNTS.items():
            for i in range(count):
                conn.execute(
                    """INSERT INTO lost_moments (id, student_id, lecture_id, slide_number, lecture_time_s, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4()), f"demo-{slide}-{i}", LECTURE_ID, slide, random.randint(slide * 600, slide * 600 + 300), now),
                )
    print(f"Seeded {sum(DEMO_COUNTS.values())} demo moments for {LECTURE_ID}.")


if __name__ == "__main__":
    main()
