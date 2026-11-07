"""Course, module, and PDF slide endpoints backed by the Canvas API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from .canvas import CanvasClient, CanvasError, is_pdf
from .db import Session
from .deps import get_session_dep

router = APIRouter(prefix="/api", tags=["canvas"])


def _course_summary(course: dict) -> dict:
    enrollments = course.get("enrollments") or []
    return {
        "id": course.get("id"),
        "name": course.get("name") or "(untitled course)",
        "course_code": course.get("course_code"),
        "workflow_state": course.get("workflow_state"),
        "enrollment_type": enrollments[0].get("type") if enrollments else None,
    }


@router.get("/courses")
def list_courses(session: Session = Depends(get_session_dep)) -> dict:
    with CanvasClient(session.access_token) as client:
        courses = client.paginate(
            "/api/v1/courses", {"enrollment_state": "active"}
        )
    return {
        "courses": [
            _course_summary(course)
            for course in courses
            if course.get("id") is not None
        ]
    }


@router.get("/courses/{course_id}/modules")
def list_modules(
    course_id: int, session: Session = Depends(get_session_dep)
) -> dict:
    with CanvasClient(session.access_token) as client:
        course = client.get(f"/api/v1/courses/{course_id}").json()
        modules = client.paginate(
            f"/api/v1/courses/{course_id}/modules", {"include[]": "items"}
        )

        file_cache: dict[int, dict] = {}
        result = []
        for module in modules:
            slides = []
            for item in module.get("items") or []:
                if item.get("type") != "File" or not item.get("content_id"):
                    continue

                file_id = int(item["content_id"])
                if file_id not in file_cache:
                    try:
                        file_cache[file_id] = client.get_file(file_id)
                    except CanvasError:
                        file_cache[file_id] = {}
                info = file_cache[file_id]
                if not info or not is_pdf(info):
                    continue

                slides.append(
                    {
                        "file_id": file_id,
                        "title": item.get("title")
                        or info.get("display_name")
                        or "Slides",
                        "filename": info.get("display_name")
                        or info.get("filename"),
                        "content_type": info.get("content-type"),
                        "size": info.get("size"),
                        "content_url": f"/api/files/{file_id}/content",
                    }
                )

            result.append(
                {
                    "id": module.get("id"),
                    "name": module.get("name") or "(untitled module)",
                    "position": module.get("position"),
                    "slides": slides,
                }
            )

    return {
        "course": {
            "id": course.get("id"),
            "name": course.get("name") or "(untitled course)",
            "course_code": course.get("course_code"),
        },
        "modules": result,
    }


@router.get("/files/{file_id}/content")
def file_content(
    file_id: int, session: Session = Depends(get_session_dep)
) -> Response:
    """Proxy a Canvas PDF through LostPoint so the browser never sees the token."""
    with CanvasClient(session.access_token) as client:
        try:
            info = client.get_file(file_id)
        except CanvasError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

        if not is_pdf(info):
            raise HTTPException(
                status_code=415, detail="Only PDF slide files can be served."
            )

        try:
            content, content_type, filename = client.download_file(file_id, info)
        except CanvasError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    safe_name = (filename or f"slides-{file_id}.pdf").replace('"', "").replace(
        "\n", " "
    )
    headers = {
        "Content-Disposition": f'inline; filename="{safe_name}"',
        "Cache-Control": "private, max-age=300",
    }
    return Response(
        content=content,
        media_type=content_type or "application/pdf",
        headers=headers,
    )
