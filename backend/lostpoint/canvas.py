"""Small Canvas LMS API client used by the LostPoint backend."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import httpx

from .config import settings

PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


class CanvasError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _next_link(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


def is_pdf(file_info: dict) -> bool:
    content_type = (
        file_info.get("content-type") or file_info.get("content_type") or ""
    ).lower()
    name = (
        file_info.get("display_name") or file_info.get("filename") or ""
    ).lower()
    return content_type in PDF_CONTENT_TYPES or name.endswith(".pdf")


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise CanvasError(
            401, "Canvas rejected the access token. Please log in again."
        )
    if response.status_code == 403:
        raise CanvasError(403, "Canvas denied access to this resource.")
    if response.status_code == 404:
        raise CanvasError(404, "Canvas resource not found.")
    if response.status_code >= 400:
        detail = response.text[:300] if response.text else response.reason_phrase
        raise CanvasError(
            502, f"Canvas API error ({response.status_code}): {detail}"
        )


class CanvasClient:
    """Per-request Canvas client authenticated with a student's access token."""

    def __init__(self, token: str):
        self._token = token
        self._client = httpx.Client(
            base_url=settings.canvas_base_url,
            timeout=settings.request_timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )

    def __enter__(self) -> "CanvasClient":
        return self

    def __exit__(self, *_exc_info) -> None:
        self._client.close()

    def get(self, path: str, params: dict | None = None) -> httpx.Response:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise CanvasError(502, f"Could not reach Canvas: {exc}") from exc
        _raise_for_status(response)
        return response

    def paginate(self, path: str, params: dict | None = None) -> list[dict]:
        query = dict(params or {})
        query.setdefault("per_page", 100)
        url: str | None = path
        first_request = True
        results: list[dict] = []
        while url:
            try:
                response = self._client.get(
                    url, params=query if first_request else None
                )
            except httpx.HTTPError as exc:
                raise CanvasError(502, f"Could not reach Canvas: {exc}") from exc
            _raise_for_status(response)
            data = response.json()
            if isinstance(data, list):
                results.extend(data)
            elif data:
                results.append(data)
            url = _next_link(response.headers.get("link"))
            first_request = False
        return results

    def get_file(self, file_id: int) -> dict:
        return self.get(f"/api/v1/files/{file_id}").json()

    def download_file(
        self, file_id: int, file_info: dict | None = None
    ) -> tuple[bytes, str, str]:
        info = file_info or self.get_file(file_id)
        download_url = info.get("url")
        if not download_url:
            raise CanvasError(404, "Canvas did not return a download URL for this file.")

        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            with httpx.Client(
                timeout=settings.request_timeout, follow_redirects=False
            ) as client:
                response = client.get(download_url, headers=headers)

                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise CanvasError(
                            502, "Canvas returned an empty file redirect."
                        )
                    target = urlparse(location)
                    base = urlparse(settings.canvas_base_url)
                    rewritten = urlunparse(
                        target._replace(scheme=base.scheme, netloc=base.netloc)
                    )
                    # Canvas validates the signed verifier against its configured
                    # hostname (usually canvas.docker), so preserve it in Host even
                    # though we connect through the base URL.
                    host_headers = dict(headers)
                    if target.netloc:
                        host_headers["Host"] = target.netloc
                    response = client.get(
                        rewritten, headers=host_headers, follow_redirects=True
                    )

                if response.status_code >= 400:
                    raise CanvasError(
                        response.status_code,
                        f"Canvas file download failed ({response.status_code}).",
                    )

                content_type = (
                    response.headers.get("content-type")
                    or info.get("content-type")
                    or "application/pdf"
                )
                filename = (
                    info.get("display_name")
                    or info.get("filename")
                    or f"slides-{file_id}.pdf"
                )
                return response.content, content_type, filename
        except httpx.HTTPError as exc:
            raise CanvasError(
                502, f"Could not download the file from Canvas: {exc}"
            ) from exc
