FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./frontend/
WORKDIR /app/frontend
RUN npm ci
WORKDIR /app
COPY frontend/src ./frontend/src
COPY frontend/*.json ./frontend/
COPY frontend/*.js ./frontend/
COPY frontend/*.ts ./frontend/
COPY frontend/index.html ./frontend/
COPY config ./config
COPY fixtures ./fixtures
RUN cd frontend && npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend
COPY config ./config
COPY fixtures ./fixtures
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
