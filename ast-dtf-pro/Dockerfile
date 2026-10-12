FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AST_DATA=/data OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home ast && mkdir /data && chown ast:ast /data
COPY --chown=ast:ast backend/ ./backend/
COPY --chown=ast:ast manage.py ./
COPY --from=frontend --chown=ast:ast /build/dist ./frontend/dist
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn","backend.api:app","--host","0.0.0.0","--port","8000","--workers","1","--no-proxy-headers"]
