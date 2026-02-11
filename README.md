# NIMS Hospital Voice Assistant

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-orange.svg)](https://openai.com)

Multilingual voice assistant for **NIMS Hospital, Hyderabad** powered by OpenAI GPT-4o-mini.

## Features

- **Text & Voice Chat**: Query hospital information via text or voice
- **Multilingual**: English, Hindi, Telugu with same-language responses
- **OpenAI Integration**: GPT-4o-mini for intelligent query processing
- **Database Tools**: Department info, facility lookup
- **Text-to-Speech**: gTTS for audio responses

## Clean Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      PRESENTATION LAYER                             │
│                        (src/main.py)                                │
│         FastAPI endpoints, HTTP handlers, WebSocket                 │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       USE CASES LAYER                               │
│              (src/orchestration/pipecat_orchestrator.py)            │
│     Business logic: language detection, query processing,           │
│     response generation, TTS audio creation                         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                ┌───────────────┴───────────────┐
                ▼                               ▼
┌───────────────────────────┐   ┌───────────────────────────────────┐
│   INFRASTRUCTURE LAYER    │   │      INFRASTRUCTURE LAYER         │
│   (src/services/)         │   │      (src/database/)              │
│                           │   │                                   │
│   openai_service.py       │   │      db_wrapper.py                │
│   - GPT-4o-mini API       │   │      - PostgreSQL queries         │
│   - Chat completions      │   │      - Departments table          │
│                           │   │      - Facilities table           │
└───────────────────────────┘   └───────────────────────────────────┘
```

## Project Structure

```
project01/
├── .env                        # API keys & DB config
├── requirements.txt            # Python dependencies
├── README.md                   # This file
│
├── src/
│   ├── main.py                 # FastAPI application (Presentation)
│   ├── config.py               # Configuration management
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   └── db_wrapper.py       # PostgreSQL queries (Infrastructure)
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   └── openai_service.py   # OpenAI GPT-4o-mini (Infrastructure)
│   │
│   └── orchestration/
│       ├── __init__.py
│       └── pipecat_orchestrator.py  # Business logic (Use Cases)
│
└── static/
    └── realtime_voice.html     # Voice demo UI
```

## Quick Start

### 1. Prerequisites

- Python 3.10+
- PostgreSQL 15+

### 2. Installation

```bash
# Create virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create `.env` file:

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini

# PostgreSQL Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DATABASE=clinic_assistant
POSTGRES_USER=clinic_user
POSTGRES_PASSWORD=your_password

# Server Configuration
SERVER_HOST=0.0.0.0
SERVER_PORT=8001
```

### 4. Database Setup

```sql
-- Create database
CREATE DATABASE clinic_assistant;

-- Departments table
CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    location VARCHAR(200),
    timings VARCHAR(100),
    head_doctor VARCHAR(100),
    contact_number VARCHAR(50)
);

-- Facilities table
CREATE TABLE facilities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    location VARCHAR(200),
    timings VARCHAR(100)
);
```

### 5. Run Server

```bash
cd src
python main.py
```

Server runs at: `http://localhost:8001`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API Root |
| `/voice` | GET | Voice Demo UI |
| `/docs` | GET | Swagger Documentation |
| `/health` | GET | Health Check |
| `/api/chat` | POST | Text Chat |
| `/api/voice` | POST | Voice (Audio) Chat |
| `/ws/voice` | WS | WebSocket Voice Stream |

### Chat API

```bash
curl -X POST http://localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Where is pharmacy?"}'
```

Response:
```json
{
  "success": true,
  "response": "The Pharmacy is located in Block A, Lobby (Ground Floor). It operates 24x7.",
  "audio_url": "/api/audio/response_xxx.mp3",
  "language": "en"
}
```

### WebSocket Voice API

Connect to `/ws/voice` for real-time voice streaming.

## Database Tools

The orchestrator queries these database tables:

| Table | Description | Key Fields |
|-------|-------------|------------|
| `departments` | Hospital departments | name, head_doctor, contact_number, location, timings |
| `facilities` | Hospital facilities | name, location, timings |

## Supported Languages

| Language | Code | TTS | Example Query |
|----------|------|-----|---------------|
| English | `en` | ✅ | "Who is the doctor in cardiology?" |
| Hindi | `hi` | ✅ | "कार्डियोलॉजी विभाग में डॉक्टर कौन है?" |
| Telugu | `te` | ✅ | "ఫార్మసీ ఎక్కడ ఉంది?" |

## Example Queries

```
English:
- "Who is the doctor in cardiology?"
- "Where is the pharmacy?"
- "What are the OPD timings?"

Hindi:
- "कार्डियोलॉजी विभाग में डॉक्टर कौन है?"
- "दवाखाना कहाँ है?"

Telugu:
- "ఫార్మసీ ఎక్కడ ఉంది?"
- "కార్డియాలజీ డాక్టర్ ఎవరు?"
```

## Development

### Run Tests

```bash
# Test orchestrator standalone
python -m src.orchestration.pipecat_orchestrator

# Test database
python -m src.database.db_wrapper
```

### Code Style

- Follow PEP 8
- Use type hints
- Document functions with docstrings
- Parameterized queries only (SQL injection safe)

## Dependencies

### Core
- **FastAPI** - Web framework
- **Uvicorn** - ASGI server
- **Pydantic** - Data validation

### AI
- **OpenAI** - GPT-4o-mini for query processing

### Voice
- **gTTS** - Google Text-to-Speech for audio responses

### Database
- **asyncpg** - PostgreSQL async driver
- **psycopg2-binary** - PostgreSQL sync driver

### Utilities
- **langdetect** - Language detection
- **httpx** - HTTP client
- **aiohttp** - Async HTTP client
- **websockets** - WebSocket support

## License

MIT License - NIMS Hospital 2024
