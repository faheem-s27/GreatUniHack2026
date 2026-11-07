#!/usr/bin/env python3
"""Print Canvas courses -> modules -> items so we can verify slide uploads.

Reads CANVAS_BASE_URL and CANVAS_API_TOKEN from backend/.env (or the
environment). File module items are resolved to their content type so we can
confirm they are PDFs before wiring the LostPoint UI.

Usage:
    python3 backend/scripts/inspect_canvas.py
    python3 backend/scripts/inspect_canvas.py --course 123
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / "backend" / ".env"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def request_json(url: str, token: str) -> tuple[object, str]:
    req = Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=20) as response:
            return json.load(response), response.headers.get("Link", "")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"HTTP {exc.code} for {url}\n{body}") from exc
    except URLError as exc:
        raise SystemExit(f"Cannot reach {url}: {exc.reason}") from exc


def next_link(header: str) -> str | None:
    for part in header.split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


def paginate(base: str, token: str, path: str, params: dict | None = None) -> list:
    query = dict(params or {})
    query.setdefault("per_page", 100)
    url = f"{base}{path}?{urlencode(query, doseq=True)}"
    results: list = []
    while url:
        data, link = request_json(url, token)
        if isinstance(data, list):
            results.extend(data)
        else:
            results.append(data)
        url = next_link(link)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course", type=int, help="only inspect this course id")
    args = parser.parse_args()

    load_env(ENV_FILE)
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    token = os.environ.get("CANVAS_API_TOKEN", "")

    if not base or not token:
        print(
            "Set CANVAS_BASE_URL and CANVAS_API_TOKEN in backend/.env "
            "(copy backend/.env.example first).",
            file=sys.stderr,
        )
        return 1

    courses = paginate(base, token, "/api/v1/courses", {"enrollment_state": "active"})
    if args.course:
        courses = [course for course in courses if course.get("id") == args.course]

    if not courses:
        print("No active courses found for this token.")
        return 0

    for course in courses:
        print(f"Course {course['id']}: {course.get('name', '(untitled)')}")
        modules = paginate(
            base,
            token,
            f"/api/v1/courses/{course['id']}/modules",
            {"include[]": "items"},
        )
        if not modules:
            print("  (no modules)")
            continue

        for module in modules:
            print(f"  Module {module['id']}: {module.get('name', '(untitled)')}")
            items = module.get("items")
            if items is None:
                items = paginate(
                    base,
                    token,
                    f"/api/v1/courses/{course['id']}/modules/{module['id']}/items",
                )
            if not items:
                print("    (no items)")
                continue

            for item in items:
                item_type = item.get("type", "?")
                title = item.get("title", "(untitled)")
                if item_type == "File" and item.get("content_id"):
                    try:
                        file_info, _ = request_json(
                            f"{base}/api/v1/files/{item['content_id']}", token
                        )
                        content_type = file_info.get("content-type", "unknown")
                        print(
                            f"    [File] {title} — {content_type} — "
                            f"file_id={item['content_id']}"
                        )
                    except SystemExit as exc:
                        print(f"    [File] {title} — file_id={item['content_id']} — {exc}")
                elif item_type in {"Page", "ExternalUrl", "ExternalTool"}:
                    print(f"    [{item_type}] {title} — skipped (not a file)")
                else:
                    print(f"    [{item_type}] {title} — skipped")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
