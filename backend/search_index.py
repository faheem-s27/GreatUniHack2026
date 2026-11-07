"""Optional semantic slide search with Chroma, merged with the keyword search.

Keyword search (SQLite FTS5, courses.py) is always on and needs nothing extra.
With LOSTPOINT_SEARCH=chroma and `pip install chromadb`, slides are also
embedded into a local Chroma index, so a question can find a slide that
explains the idea in different words ("how is data kept for later" finds a
slide about storage). Both result lists are merged with reciprocal rank
fusion, so a slide found by both ranks highest.

The default embedding model (all-MiniLM-L6-v2, about 80 MB) is downloaded
the first time it is used and runs locally: slide text never leaves the
server. If Chroma is missing or fails, search quietly falls back to keywords.

  python search_index.py reindex     embed every stored slide (after enabling Chroma)
"""

import logging
import sys

from config import settings

log = logging.getLogger("lostpoint.search")
COLLECTION = "slides"
RRF_K = 60  # standard reciprocal-rank-fusion constant

_collection = None
_disabled_reason: str | None = None


def enabled() -> bool:
    return settings().search == "chroma" and _get_collection() is not None


def _get_collection():
    global _collection, _disabled_reason
    if settings().search != "chroma":
        return None
    if _collection is None and _disabled_reason is None:
        try:
            import chromadb

            client = chromadb.PersistentClient(path=settings().chroma_dir)
            _collection = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        except Exception as e:  # not installed, or the index could not be opened
            _disabled_reason = str(e)
            log.warning("Semantic search unavailable, using keyword search only: %s", e)
    return _collection


def _doc(row) -> str:
    return "\n".join(filter(None, [row["title"], row["topic"], row["body"]]))[:4000]


def index_lecture(conn, lecture_id: str) -> int:
    """Re-embed one lecture's slides. Returns how many slides were indexed."""
    col = _get_collection()
    if col is None:
        return 0
    rows = conn.execute(
        """SELECT s.lecture_id, s.slide_number, s.title, s.topic, s.body, l.course_id, l.week
           FROM slides s JOIN lectures l ON l.id = s.lecture_id WHERE s.lecture_id = ?""",
        (lecture_id,),
    ).fetchall()
    try:
        col.delete(where={"lecture_id": lecture_id})
        rows = [r for r in rows if _doc(r).strip()]  # picture-only slides have nothing to embed
        if rows:
            col.add(
                ids=[f"{r['lecture_id']}:{r['slide_number']}" for r in rows],
                documents=[_doc(r) for r in rows],
                metadatas=[{"lecture_id": r["lecture_id"], "slide_number": r["slide_number"],
                            "course_id": r["course_id"], "week": r["week"] if r["week"] is not None else -1} for r in rows],
            )
    except Exception as e:
        log.warning("Could not index %s for semantic search: %s", lecture_id, e)
        return 0
    return len(rows)


def semantic_hits(q: str, course_id: str | None, lecture_id: str | None, limit: int) -> list[tuple[str, int]]:
    """(lecture_id, slide_number) pairs, best first. Empty if Chroma is off or fails."""
    col = _get_collection()
    if col is None:
        return []
    filters = [f for f in ({"course_id": course_id} if course_id else None, {"lecture_id": lecture_id} if lecture_id else None) if f]
    where = filters[0] if len(filters) == 1 else ({"$and": filters} if filters else None)
    try:
        res = col.query(query_texts=[q], n_results=limit, where=where)
    except Exception as e:
        log.warning("Semantic search failed, using keyword search only: %s", e)
        return []
    return [(m["lecture_id"], int(m["slide_number"])) for m in (res.get("metadatas") or [[]])[0]]


def fuse(keyword: list[tuple[str, int]], semantic: list[tuple[str, int]], limit: int) -> list[tuple[tuple[str, int], str]]:
    """Reciprocal rank fusion of two ranked lists. Returns (key, how it matched), best first."""
    scores: dict[tuple[str, int], float] = {}
    found: dict[tuple[str, int], set] = {}
    for name, ranked in (("keyword", keyword), ("meaning", semantic)):
        for rank, key in enumerate(ranked):
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
            found.setdefault(key, set()).add(name)
    best = sorted(scores, key=lambda k: -scores[k])[:limit]
    return [(k, "both" if len(found[k]) == 2 else next(iter(found[k]))) for k in best]


def reindex_all() -> int:
    from db import connect, init_db

    init_db()
    if _get_collection() is None:
        sys.exit(f"Semantic search is off: set LOSTPOINT_SEARCH=chroma and pip install chromadb ({_disabled_reason or 'disabled'})")
    total = 0
    with connect() as conn:
        for (lecture_id,) in conn.execute("SELECT id FROM lectures").fetchall():
            n = index_lecture(conn, lecture_id)
            print(f"{lecture_id}: {n} slides")
            total += n
    return total


if __name__ == "__main__":
    if sys.argv[1:] != ["reindex"]:
        sys.exit(__doc__)
    print(f"Indexed {reindex_all()} slides.")
