# ⚖️ LegalMind — Production-Ready AI Legal Assistant

> A production-oriented Retrieval-Augmented Generation (RAG) application that enables users to query legal documents using Hybrid Search, Cross-Encoder Reranking, and modern backend engineering practices.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Async-green)
![Next.js](https://img.shields.io/badge/Next.js-14-black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-blue)
![Redis](https://img.shields.io/badge/Redis-Cache-red)
![Docker](https://img.shields.io/badge/Docker-Containerized-blue)

---

## 🚀 Overview

LegalMind is an end-to-end AI legal assistant built with a production-first mindset. Instead of relying solely on LLMs, it combines retrieval, reranking, caching, authentication, and scalable backend architecture to deliver grounded responses from legal documents.

The project demonstrates backend engineering and production-ready software development practices.

---

## ✨ Features

* 📄 Upload and process legal documents
* 🤖 Retrieval-Augmented Generation (RAG)
* 🔍 Hybrid Search (Dense + BM25)
* 🎯 Cross-Encoder Reranking
* ⚡ Async FastAPI backend
* 🔐 JWT Authentication
* 📦 PostgreSQL + pgvector
* 🚀 Redis Caching
* 🚦 Redis Rate Limiting
* 📊 Structured Logging
* 🩺 Health Monitoring
* 🐳 Fully Dockerized
* 🎨 Responsive Next.js Frontend

---

# 🏗️ Architecture

```text
                        User
                          │
                          ▼
                  Next.js Frontend
                          │
                          ▼
                    FastAPI Backend
                          │
         ┌────────────────┴──────────────┐
         ▼                               ▼
 Authentication                   Query Pipeline
         │                               │
         ▼                               ▼
 PostgreSQL                     Hybrid Retrieval
(User & Metadata)            Dense + BM25 Search
                                        │
                                        ▼
                            Cross Encoder Reranker
                                        │
                                        ▼
                               Large Language Model
                                        │
                                        ▼
                              Grounded AI Response
```

---

# ⚙️ Tech Stack

### Backend

* FastAPI
* SQLAlchemy (Async)
* PostgreSQL
* pgvector
* Redis
* JWT Authentication

### AI

* Sentence Transformers
* Hybrid Retrieval
* Cross Encoder
* Groq / Gemini
* RAG Pipeline

### Frontend

* Next.js 14
* React
* TypeScript

### DevOps

* Docker
* Docker Compose
* Environment Configuration
* Structured Logging
* Sentry Monitoring

---

# 🧠 RAG Pipeline

```text
Document Upload
      │
      ▼
Text Extraction
      │
      ▼
Chunking
      │
      ▼
Embedding Generation
      │
      ▼
Vector Storage (pgvector)
      │
      ▼
User Query
      │
      ▼
Hybrid Retrieval
(Dense + BM25)
      │
      ▼
Cross Encoder Reranking
      │
      ▼
Top Relevant Context
      │
      ▼
LLM Response Generation
      │
      ▼
Grounded Answer
```

---

# 📈 Production Highlights

✔ Modular Architecture

✔ Fully Asynchronous Backend

✔ Dependency Injection

✔ Vector Database Integration

✔ Hybrid Search Retrieval

✔ Cross-Encoder Reranking

✔ Redis Caching

✔ API Rate Limiting

✔ JWT Authentication

✔ Dockerized Deployment

✔ Structured Logging

✔ Error Monitoring

---

# 📊 Performance

> Replace these numbers with your own benchmark results.

| Metric                   |                              Improvement |
| ------------------------ | ---------------------------------------: |
| Retrieval Accuracy       |  **+18–25%** (Hybrid Search + Reranking) |
| Average Response Latency |       **30–40% lower** using Redis Cache |
| API Throughput           |              Improved with Async FastAPI |
| Retrieval Quality        | Better relevance than vector-only search |

---

# 📂 Project Structure

```text
legal_Mind/

├── backend/
│   ├── api/
│   ├── auth/
│   ├── core/
│   ├── db/
│   ├── middleware/
│   ├── services/
│  
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── context/
│   └── lib/
│
├── docker-compose.yml
├── README.md
└── .env.example
```

---

# 🐳 Running with Docker

```bash
git clone https://github.com/Subhashree-Nayak507/legal_Mind.git

cd legal_Mind

docker compose up --build
```

Stop containers

```bash
docker compose down
```

Remove containers with volumes

```bash
docker compose down -v
```

---

# 🎯 Engineering Concepts Demonstrated

* Retrieval-Augmented Generation (RAG)
* Hybrid Search
* Vector Databases
* Cross-Encoder Reranking
* Async Programming
* Backend System Design
* Authentication
* Caching Strategies
* API Design
* Dockerized Deployment
* Production Logging
* Error Monitoring
