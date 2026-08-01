# ── Stage 1: build the Next.js frontend as static files ────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
ENV NEXT_PUBLIC_API_URL=/api/v1
RUN npm run build

# ── Stage 2: backend + the built frontend, served as one process ───────────
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc g++ && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend-build /frontend/out ./app/static

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]