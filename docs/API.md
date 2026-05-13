# Tokenized Assets Pipeline API

Complete FastAPI backend with ARQ job queue for processing tokenized assets data extraction.

## Architecture

```
┌───────────┐       ┌───────────┐       ┌──────────────┐
│  React    │──────▶│  FastAPI  │──────▶│     ARQ      │
│ Frontend  │       │   Server  │       │ Job Queue    │
└───────────┘       └───────────┘       └──────────────┘
                           │                    │
                           ▼                    ▼
                    ┌───────────┐       ┌──────────────┐
                    │ PostgreSQL│       │   Workers    │
                    │ Database  │       │  (Pipeline)  │
                    └───────────┘       └──────────────┘
```

## Components

### FastAPI Server (`src/api/server.py`)
- REST API endpoints
- CORS support for frontend
- Health checks
- Job management via ARQ

### ARQ Worker (`src/api/arq_worker.py`)
- Background job processing
- Pipeline execution
- Database updates
- Error handling

### Database Layer (`src/api/database.py`)
- Async PostgreSQL connection
- Company queries
- Pipeline run tracking
- Result aggregation

## Endpoints

### POST /run
Run pipeline for a single company.

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Securitize",
    "domain": "securitize.io",
    "timeout": 180
  }'
```

Response:
```json
{
  "job_id": "abc123",
  "company_name": "Securitize",
  "domain": "securitize.io",
  "status": "queued"
}
```

### POST /batch
Run pipeline for multiple companies.

```bash
curl -X POST http://localhost:8000/batch \
  -H "Content-Type: application/json" \
  -d '{
    "companies": [
      {"company_name": "Company 1", "domain": "company1.com"},
      {"company_name": "Company 2", "domain": "company2.com"}
    ],
    "max_concurrent": 2
  }'
```

### GET /companies
Get all processed companies.

```bash
curl http://localhost:8000/companies?limit=10&status=completed
```

### GET /company/{domain}
Get detailed company information.

```bash
curl http://localhost:8000/company/securitize.io
```

### GET /result/{job_id}
Get job status and result.

```bash
curl http://localhost:8000/result/abc123
```

### GET /health
Health check endpoint.

```bash
curl http://localhost:8000/health
```

## Environment Variables

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=fiftyone_insights

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# SearXNG
SEARXNG_URL=http://localhost:8080

# LLM Provider
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...

# Alternative providers
ANTHROPIC_API_KEY=...
ZAI_API_KEY=...
```

## Running the Stack

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api worker

# Stop services
docker-compose down
```

### Running Locally

```bash
# Start PostgreSQL and Redis
docker-compose up -d postgres redis searxng

# Run API server
uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000

# Run worker (in separate terminal)
python -m src.api.worker
```

## Testing

```bash
# Run integration tests
pytest tests/api/test_server.py -v

# Run manual test script
python scripts/test_api_integration.py
```

## Frontend Integration

The React frontend connects to the API at `http://localhost:8000` (or configured via `VITE_API_URL`).

```typescript
// Frontend API call
const response = await axios.post(`${apiUrl}/run`, {
  company_name: "Securitize",
  domain: "securitize.io",
  timeout: 180,
});

const { job_id } = response.data;

// Poll for results
const result = await axios.get(`${apiUrl}/result/${job_id}`);
```

## Job Queue Flow

1. **Submit**: Frontend sends request to `/run` or `/batch`
2. **Queue**: API enqueues job(s) to Redis via ARQ
3. **Process**: Worker(s) pick up jobs and run pipeline
4. **Store**: Results saved to PostgreSQL
5. **Poll**: Frontend polls `/result/{job_id}` for updates
6. **Retrieve**: Frontend fetches details from `/company/{domain}`

## Database Schema

See `database/schema.sql` for full schema. Key tables:
- `companies`: Company information
- `pipeline_runs`: Extraction run tracking
- `llm_call_logs`: Per-call cost tracking
- `products`, `features`, `integrations`: Extracted data

## Monitoring

### Health Checks
```bash
curl http://localhost:8000/health
```

### Redis Queue
```bash
redis-cli
> KEYS arq:*
> LLEN arq:queue
```

### Database
```bash
psql -U postgres -d fiftyone_insights
SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 10;
```

## Troubleshooting

### Jobs not processing
- Check worker logs: `docker-compose logs worker`
- Verify Redis connection: `redis-cli ping`
- Check database connectivity

### Connection errors
- Ensure PostgreSQL is running: `docker-compose ps postgres`
- Verify environment variables
- Check network configuration in docker-compose.yml

### High memory usage
- Reduce worker replicas in docker-compose.yml
- Adjust `max_jobs` in `WorkerSettings`
- Decrease `job_timeout` for faster cleanup
