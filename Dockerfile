# One container serves the API, the WebSockets and the built frontend on port 8000.
#   docker build -t lostpoint .
#   docker run -p 8000:8000 -v lostpoint-data:/data -e LOSTPOINT_STAFF_CODE=change-me lostpoint
# Or: docker compose up --build

# --- build the frontend --------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- the backend -----------------------------------------------------------------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOSTPOINT_DB=/data/lostpoint.db \
    LOSTPOINT_CHROMA_DIR=/data/chroma \
    LOSTPOINT_STATIC_DIR=/app/static
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/*.py ./
COPY backend/lostpoint ./lostpoint
COPY backend/prompts ./prompts
COPY --from=frontend /frontend/dist ./static
RUN useradd --create-home --uid 1000 lostpoint && mkdir -p /data && chown lostpoint /data
USER lostpoint
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
