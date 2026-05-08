<div align="center">

# 🧠 NeuroSeek AI

**A self-hosted, multi-agent AI research platform that runs on a single 4 GB VPS — no GPU required.**

Not a chatbot. A full research workspace that ingests your documents, searches the live web, and produces **cited, downloadable research reports** in Markdown and PDF.

[![Django](https://img.shields.io/badge/Django-5.0-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Go](https://img.shields.io/badge/Go-1.22-00ADD8?logo=go&logoColor=white)](https://go.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-0.7-4169E1)](https://github.com/pgvector/pgvector)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## ✨ What it does

NeuroSeek AI is a research assistant you fully control. Drop in a question and it will:

1. **Plan** the research — decompose your query into sub-questions.
2. **Retrieve** evidence from **your documents** (RAG over PDF / DOCX / TXT / MD / CSV) **and the live web** (via self-hosted SearXNG).
3. **Reason** over the results using an orchestrated, multi-step LLM workflow.
4. **Write** a structured, **citation-backed** report — streamed live to your browser as it's generated.
5. **Export** the result as Markdown or PDF.

All of this runs on a **single 4 GB VPS with no GPU** thanks to careful architectural choices (see [Architecture](#-architecture)).

---

## 🎯 Key Features

- 📄 **Document RAG** — Upload PDFs, Word docs, plain text, Markdown, or CSV files. Documents are chunked, embedded, and stored in pgvector.
- 🌐 **Live web research** — Pulls real-time results from a self-hosted SearXNG instance, then scrapes pages with a cascading fallback chain.
- 🔬 **Multi-step research workflow** — An LLM-orchestrated agent that plans, retrieves, evaluates, and writes — not a single-shot chatbot.
- 🔀 **Hybrid retrieval** — Combines **dense** (pgvector cosine) and **sparse** (Postgres FTS) search, fused with **Reciprocal Rank Fusion** for higher recall and precision than either alone.
- 📡 **Live progress streaming** — A Go WebSocket microservice pushes step-by-step progress to the browser as the agent works.
- 📑 **Cited reports** — Every claim links back to its source. Export as Markdown or polished PDF (rendered by WeasyPrint).
- 🪶 **Runs on 4 GB RAM, no GPU** — CPU-only embeddings, cloud-hosted LLM inference, and a lightweight Go service for real-time fanout.
- 🔌 **Pluggable LLM adapter** — Swap providers with a single config change. Ships with [Ollama Cloud](https://ollama.com/cloud) (`gpt-oss:120b-cloud`); easily add OpenAI, Anthropic, or local Ollama.

---

## 🏗 Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │                  Browser (vanilla JS)        │
                    └───────────────┬─────────────────┬───────────┘
                                    │ HTTP/REST       │ WebSocket
                                    ▼                 ▼
            ┌───────────────────────────┐   ┌────────────────────┐
            │  Django 5 + DRF (Python)  │   │  Go microservice   │
            │  ─ Auth / CRUD            │   │  ─ WS fanout only  │
            │  ─ Agent orchestration    │   │  ─ ~30 MB resident │
            │  ─ RAG pipeline           │   │  (vs ~1 GB Daphne) │
            └────────────┬──────────────┘   └─────────┬──────────┘
                         │                            │
                         ▼                            ▼
                ┌────────────────────────────────────────┐
                │              Redis (pub/sub)            │
                │  ─ Cache  ─ Celery broker  ─ WS bus     │
                └────────────────────────────────────────┘
                         │
       ┌─────────────────┼─────────────────┬─────────────────┐
       ▼                 ▼                 ▼                 ▼
┌──────────────┐ ┌──────────────┐ ┌────────────────┐ ┌──────────────┐
│ PostgreSQL   │ │  Celery      │ │   SearXNG      │ │ Ollama Cloud │
│ + pgvector   │ │  workers     │ │ (self-hosted)  │ │ gpt-oss:120b │
│ + FTS (RRF)  │ │              │ │                │ │              │
└──────────────┘ └──────────────┘ └────────────────┘ └──────────────┘
```

### Architecture highlights

| Decision | What | Why |
|---|---|---|
| **Polyglot stack** | Django for AI/CRUD, Go for WebSocket fanout via Redis pub/sub | Daphne+Channels would eat ~1 GB. The Go service is **~30 MB resident** — ~33× smaller. |
| **Hybrid retrieval** | pgvector cosine + Postgres FTS, fused with **Reciprocal Rank Fusion** | Dense alone misses keyword matches; sparse alone misses semantics. RRF gets the best of both with no learned re-ranker. |
| **CPU-only embeddings** | `bge-small-en-v1.5` (384-dim) via sentence-transformers | Tiny, fast, and runs comfortably on a 4 GB VPS without a GPU. |
| **Pluggable LLM adapter** | Ollama Cloud as default (`gpt-oss:120b-cloud`) | Zero VPS RAM for the model. One config change to swap providers. |
| **Cascading scrapers** | trafilatura → BeautifulSoup → [Jina Reader](https://jina.ai/reader) fallback | Handles clean blogs *and* hostile/JS-heavy sites without writing a custom scraper per source. |
| **PDF rendering** | WeasyPrint | Pure-Python HTML→PDF, no headless Chrome. Keeps the footprint tiny. |

---

## 🛠 Tech Stack

**Backend** &nbsp;Django 5 · Django REST Framework · Celery
**Microservice** &nbsp;Go · Gorilla WebSocket · Redis pub/sub
**Database** &nbsp;PostgreSQL 16 + pgvector + FTS
**Cache / Broker / Bus** &nbsp;Redis 7
**AI / ML** &nbsp;sentence-transformers (`bge-small-en-v1.5`) · Ollama Cloud (`gpt-oss:120b-cloud`)
**Search** &nbsp;SearXNG (self-hosted)
**Scraping** &nbsp;trafilatura · BeautifulSoup · Jina Reader
**Reports** &nbsp;WeasyPrint (PDF) · Markdown
**Frontend** &nbsp;Vanilla JS (no framework, no build step)
**Infra** &nbsp;Docker · Docker Compose · NGINX

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- ~4 GB RAM minimum
- An [Ollama Cloud](https://ollama.com/cloud) API key (or your preferred LLM provider — see [Configuration](#-configuration))

### 1. Clone

```bash
git clone https://github.com/<your-username>/neuroseek-ai.git
cd neuroseek-ai
```

### 2. Configure

```bash
cp .env.example .env
# Open .env and fill in:
#   - DJANGO_SECRET_KEY
#   - POSTGRES_PASSWORD
#   - OLLAMA_API_KEY  (or your chosen provider's key)
#   - SEARXNG_SECRET
```

### 3. Run

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

### 4. Open

Visit **http://localhost** and start your first research session.

---

## ⚙️ Configuration

Key environment variables (full list in `.env.example`):

| Variable | Description | Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Django secret key | _required_ |
| `DJANGO_DEBUG` | Debug mode | `False` |
| `POSTGRES_*` | Postgres connection | _required_ |
| `REDIS_URL` | Redis URL | `redis://redis:6379/0` |
| `LLM_PROVIDER` | `ollama_cloud` / `openai` / `anthropic` / `ollama_local` | `ollama_cloud` |
| `LLM_MODEL` | Model name | `gpt-oss:120b-cloud` |
| `OLLAMA_API_KEY` | Ollama Cloud API key | _required if using Ollama Cloud_ |
| `EMBEDDING_MODEL` | Sentence-transformers model | `BAAI/bge-small-en-v1.5` |
| `SEARXNG_URL` | SearXNG endpoint | `http://searxng:8080` |
| `WS_SERVICE_URL` | Go WS microservice URL | `http://ws:8081` |
| `RRF_K` | Reciprocal Rank Fusion constant | `60` |
| `MAX_UPLOAD_MB` | Max file upload size | `25` |

### Swapping the LLM provider

The LLM is accessed through a single adapter interface (`apps/llm/adapters/`). To switch providers, change `LLM_PROVIDER` and `LLM_MODEL` in `.env`. Built-in adapters:

- `ollama_cloud` — recommended for low-RAM VPS deployments
- `ollama_local` — for local Ollama servers
- `openai` — OpenAI-compatible APIs
- `anthropic` — Claude models

---

## 📁 Project Structure

```
neuroseek-ai/
├── apps/
│   ├── accounts/          # Auth & user management
│   ├── documents/         # Upload, parse, chunk, embed
│   ├── retrieval/         # pgvector + FTS + RRF fusion
│   ├── search/            # SearXNG client + scraper cascade
│   ├── agents/            # Multi-step research orchestration
│   ├── reports/           # Markdown + WeasyPrint PDF
│   └── llm/               # Pluggable provider adapters
├── ws-service/            # Go WebSocket microservice
│   ├── main.go
│   └── internal/
├── frontend/              # Vanilla JS, no build step
│   ├── index.html
│   └── static/
├── compose/               # Docker Compose configs
│   ├── django/
│   ├── nginx/
│   └── searxng/
├── docker-compose.yml
├── manage.py
└── requirements.txt
```

---

## 🔬 How the research workflow works

```
User query
   │
   ▼
[1] Plan        ─ LLM decomposes query into sub-questions
   │
   ▼
[2] Retrieve    ─ For each sub-question, run hybrid retrieval:
   │              ┌─ Document RAG  (pgvector + FTS, fused via RRF)
   │              └─ Web search    (SearXNG → cascading scrapers)
   ▼
[3] Evaluate    ─ LLM scores evidence relevance, drops noise
   │
   ▼
[4] Synthesize  ─ LLM writes section-by-section with inline citations
   │              (each step streamed live to the browser via Go WS)
   ▼
[5] Export      ─ Render Markdown + PDF (WeasyPrint)
```

Every step's progress is published to Redis and fanned out to the browser by the Go WebSocket microservice — so the user sees the agent thinking, retrieving, and writing in real time.

---

## 📊 Why these choices?

- **Why Go for WebSockets?** Daphne + Channels was using ~1 GB of resident RAM for a workload that's almost entirely I/O-bound message fanout. A 200-line Go service does the same job in ~30 MB and frees up ~1 GB on a 4 GB box.
- **Why hybrid retrieval with RRF?** Dense embeddings nail semantic similarity but miss exact keywords (model numbers, names, codes). FTS handles those. RRF needs no training data — it just fuses ranks.
- **Why Ollama Cloud over local LLMs?** A 120B-class model can't run on a 4 GB VPS. Renting GPU minutes is expensive and slow. Ollama Cloud gives you frontier-quality output at per-token pricing with zero local RAM cost.
- **Why vanilla JS?** No build step, no node_modules, no version churn. The frontend is ~1500 lines and ships as static files behind NGINX.

---

## 🗺 Roadmap

- [ ] Per-user document collections / workspaces
- [ ] Conversation memory across sessions
- [ ] Fine-grained citation linking (claim → exact span)
- [ ] More embedding models (multilingual)
- [ ] Optional re-ranker (e.g. `bge-reranker-base`)
- [ ] Public demo deployment

---

## 🤝 Contributing

Issues and PRs are welcome. If you're building something similar or want to add an LLM adapter, open an issue first to discuss.

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

## 👤 Author

**Rony Zeenaldeen** — Back-End & AI/ML Engineer

Built end-to-end: backend, agent orchestration, Go microservice, frontend, infra. Open to **Backend** / **AI Engineering** roles.

- 📧 ronizenalden@gmail.com
- 💼 [LinkedIn](www.linkedin.com/in/rony-zeenaldeen-b288112ab)
- 🐙 [GitHub](https://github.com/Rony-ZenAlden/)

---

<div align="center">

If NeuroSeek AI is useful to you, please ⭐ star the repo — it really helps.

</div>
