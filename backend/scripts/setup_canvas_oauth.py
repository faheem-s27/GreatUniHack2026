#!/usr/bin/env python3
"""Provision the Canvas OAuth developer key and demo student for LostPoint.

Run this after Canvas is running and backend/.env contains CANVAS_BASE_URL and
CANVAS_API_TOKEN for an admin user:

    python3 backend/scripts/setup_canvas_oauth.py

The script is idempotent. It creates (or updates) a developer key named
"LostPoint", turns on its account binding, creates a demo student, enrolls the
student in the demo course, and writes the OAuth settings to backend/.env.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / "backend" / ".env"
DEFAULT_REDIRECT_URIS = [
    "http://localhost:5173/api/auth/canvas/callback",
    "http://localhost:8000/api/auth/canvas/callback",
]


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def upsert_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in values:
                output.append(f"{key}={values[key]}")
                seen.add(key)
                continue
        output.append(line)

    if output and output[-1].strip():
        output.append("")
    for key, value in values.items():
        if key not in seen:
            output.append(f"{key}={value}")

    path.write_text("\n".join(output).rstrip() + "\n")


def api_request(
    base: str,
    token: str,
    method: str,
    path: str,
    data: dict | None = None,
):
    body = urlencode(data, doseq=True).encode() if data else None
    request = Request(
        f"{base}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", "replace")[:600]
        raise SystemExit(
            f"Canvas API {method} {path} failed with HTTP {exc.code}:\n{body_text}"
        ) from exc
    except URLError as exc:
        raise SystemExit(f"Cannot reach Canvas at {base}: {exc.reason}") from exc


def find_or_create_developer_key(
    base: str,
    token: str,
    redirect_uris: list[str],
    admin_email: str,
) -> dict:
    keys = api_request(
        base, token, "GET", "/api/v1/accounts/1/developer_keys?per_page=100"
    )
    existing = next((key for key in keys or [] if key.get("name") == "LostPoint"), None)
    payload = {
        "developer_key[name]": "LostPoint",
        "developer_key[email]": admin_email,
        "developer_key[redirect_uris][]": redirect_uris,
        "developer_key[require_scopes]": "false",
    }
    if existing:
        key = api_request(
            base,
            token,
            "PUT",
            f"/api/v1/developer_keys/{existing['id']}",
            payload,
        )
    else:
        key = api_request(
            base, token, "POST", "/api/v1/accounts/1/developer_keys", payload
        )

    # A new developer key starts with its account binding "off". OAuth2 requires
    # the binding to be "on" before the key can authorize users.
    api_request(
        base,
        token,
        "POST",
        f"/api/v1/accounts/1/developer_keys/{key['id']}/developer_key_account_bindings",
        {"developer_key_account_binding[workflow_state]": "on"},
    )
    return key


def find_or_create_student(
    base: str,
    token: str,
    name: str,
    email: str,
    password: str,
) -> dict:
    users = api_request(
        base, token, "GET", "/api/v1/accounts/1/users?per_page=100"
    )
    existing = next(
        (user for user in users or [] if user.get("login_id") == email), None
    )
    if existing:
        return existing

    return api_request(
        base,
        token,
        "POST",
        "/api/v1/accounts/1/users",
        {
            "user[name]": name,
            "user[short_name]": name,
            "user[sortable_name]": ", ".join(reversed(name.split(" ", 1))),
            "pseudonym[unique_id]": email,
            "pseudonym[password]": password,
            "communication_channel[address]": email,
            "communication_channel[type]": "email",
        },
    )


def publish_course(base: str, token: str, course_id: int) -> None:
    """Make the demo course and its modules visible to students."""
    try:
        course = api_request(base, token, "GET", f"/api/v1/courses/{course_id}")
    except SystemExit:
        return

    if course.get("workflow_state") != "available":
        api_request(
            base,
            token,
            "PUT",
            f"/api/v1/courses/{course_id}",
            {"course[event]": "offer"},
        )

    modules = api_request(
        base,
        token,
        "GET",
        f"/api/v1/courses/{course_id}/modules?per_page=100",
    )
    for module in modules or []:
        if module.get("published") is False:
            api_request(
                base,
                token,
                "PUT",
                f"/api/v1/courses/{course_id}/modules/{module['id']}",
                {"module[published]": "true"},
            )


def enroll_student(base: str, token: str, course_id: int, user_id: int) -> None:
    try:
        enrollments = api_request(
            base,
            token,
            "GET",
            f"/api/v1/courses/{course_id}/enrollments?user_id={user_id}&per_page=100",
        )
    except SystemExit:
        print(
            f"warning: could not read enrollments for course {course_id}; skipping",
            file=sys.stderr,
        )
        return

    already_enrolled = any(
        enrollment.get("user_id") == user_id
        and enrollment.get("type") == "StudentEnrollment"
        for enrollment in enrollments or []
    )
    if already_enrolled:
        return

    api_request(
        base,
        token,
        "POST",
        f"/api/v1/courses/{course_id}/enrollments",
        {
            "enrollment[user_id]": user_id,
            "enrollment[type]": "StudentEnrollment",
            "enrollment[enrollment_state]": "active",
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--course",
        type=int,
        default=int(os.environ.get("CANVAS_DEMO_COURSE_ID", "1")),
        help="Canvas course id to enroll the demo student in (default: 1)",
    )
    parser.add_argument(
        "--student-email",
        default=os.environ.get("CANVAS_STUDENT_EMAIL", "student@lostpoint.local"),
    )
    parser.add_argument(
        "--student-password",
        default=os.environ.get("CANVAS_STUDENT_PASSWORD", "lostpoint-student"),
    )
    parser.add_argument(
        "--student-name",
        default=os.environ.get("CANVAS_STUDENT_NAME", "Demo Student"),
    )
    parser.add_argument(
        "--admin-email",
        default=os.environ.get("CANVAS_ADMIN_EMAIL", "admin@lostpoint.local"),
    )
    args = parser.parse_args()

    load_env(ENV_FILE)
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    token = os.environ.get("CANVAS_API_TOKEN", "")
    if not base or not token:
        print(
            "Set CANVAS_BASE_URL and CANVAS_API_TOKEN in backend/.env first.",
            file=sys.stderr,
        )
        return 1

    print(f"Using Canvas at {base}")
    key = find_or_create_developer_key(
        base, token, DEFAULT_REDIRECT_URIS, args.admin_email
    )
    student = find_or_create_student(
        base,
        token,
        args.student_name,
        args.student_email,
        args.student_password,
    )
    try:
        enroll_student(base, token, args.course, student["id"])
        publish_course(base, token, args.course)
        enrolled_course = args.course
    except SystemExit as exc:
        print(f"warning: {exc}", file=sys.stderr)
        enrolled_course = None

    env_values = {
        "CANVAS_BASE_URL": base,
        "CANVAS_API_TOKEN": token,
        "CANVAS_CLIENT_ID": str(key["id"]),
        "CANVAS_CLIENT_SECRET": key["api_key"],
        "CANVAS_REDIRECT_URI": DEFAULT_REDIRECT_URIS[0],
        "FRONTEND_ORIGIN": os.environ.get(
            "FRONTEND_ORIGIN", "http://localhost:5173"
        ),
        "CANVAS_DEMO_COURSE_ID": str(args.course),
    }
    if not os.environ.get("SESSION_SECRET"):
        env_values["SESSION_SECRET"] = secrets.token_urlsafe(48)
    upsert_env(ENV_FILE, env_values)

    print("\nCanvas OAuth configured")
    print(f"  Client ID:     {key['id']}")
    print("  Client secret: written to backend/.env")
    print(f"  Redirect URI:  {DEFAULT_REDIRECT_URIS[0]}")
    print("\nDemo student")
    print(f"  Email:    {args.student_email}")
    print(f"  Password: {args.student_password}")
    if enrolled_course:
        print(f"  Enrolled in course {enrolled_course}")
    print("\nStart the backend from backend/:")
    print("  uvicorn main:app --reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
