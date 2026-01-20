# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GFX Sync Agent - NAS JSON to Supabase sync agent for PokerGFX data. Monitors NAS directories for JSON files and synchronizes them to Supabase in normalized format.

## Build & Development Commands

```bash
# Install dependencies (dev mode)
pip install -e ".[dev]"

# Run the agent
python -m src.sync_agent.main_v3

# Run with Docker
docker compose up -d

# Lint
ruff check src/ --fix

# Test (single file - recommended)
pytest tests/test_batch_queue.py -v

# Test (all with coverage)
pytest tests/ -v --cov=src
```

### Dashboard Commands

```bash
cd dashboard
npm install
npm run dev      # Dev server at http://localhost:3000
npm run build    # Production build
npm run lint     # ESLint
```

## Architecture

```
NAS Storage → Polling Watcher → SyncService → Supabase Cloud
   (JSON)       (watchdog)        (httpx)       (PostgreSQL)
```

### SyncAgent Task Structure

`SyncAgent.start()` runs 4 parallel asyncio tasks:
1. `_scan_existing_files()` - Initial full scan on startup
2. `watcher.start()` - Continuous file polling (2s interval)
3. `_process_offline_queue_loop()` - Retry failed records (60s interval)
4. `_watch_registry_changes()` - Hot-reload PC registry (30s interval)

### Core Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `SyncAgent` | `src/sync_agent/core/agent.py` | Main orchestrator - 4 parallel tasks |
| `SyncService` | `src/sync_agent/core/sync_service_v3.py` | Sync logic (realtime + batch) |
| `PollingWatcher` | `src/sync_agent/watcher/polling_watcher.py` | File change detection (mtime-based) |
| `BatchQueue` | `src/sync_agent/queues/batch_queue.py` | In-memory batch (500/5s) |
| `OfflineQueue` | `src/sync_agent/queues/offline_queue.py` | SQLite failover queue + Dead Letter Queue |
| `SupabaseClient` | `src/sync_agent/db/supabase_client.py` | httpx-based REST client |
| `JsonParser` | `src/sync_agent/core/json_parser.py` | JSON parsing + file_hash (SHA-256) |
| `PCRegistry` | `src/sync_agent/watcher/registry.py` | PC config from `config/pc_registry.json` |
| `Settings` | `src/sync_agent/config/settings.py` | pydantic-settings (env prefix: `GFX_SYNC_`) |

### Data Flow

1. **Created files** → Immediate single upsert (realtime path)
2. **Modified files** → BatchQueue → Batch upsert (500 records / 5 seconds)
3. **Network failure** → OfflineQueue (SQLite) → Periodic retry (60s)
4. **Max retries exceeded** → Dead Letter Queue (manual intervention)

### Error Handling

- `RateLimitError` (HTTP 429): Exponential backoff with jitter
- Parse errors: File moved to `_error/` folder
- Network failures: Queued to SQLite OfflineQueue

## PC Registry Format

Located at `{NAS_BASE_PATH}/config/pc_registry.json`:

```json
{
  "pcs": [
    { "id": "PC01", "watch_path": "PC01/hands", "enabled": true },
    { "id": "PC02", "watch_path": "PC02/hands", "enabled": false }
  ]
}
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GFX_SYNC_SUPABASE_URL` | Supabase project URL | Required |
| `GFX_SYNC_SUPABASE_SECRET_KEY` | Supabase service_role key | Required |
| `GFX_SYNC_NAS_BASE_PATH` | NAS mount path | `/app/data` |
| `GFX_SYNC_POLL_INTERVAL` | File polling interval (seconds) | `2.0` |
| `GFX_SYNC_BATCH_SIZE` | Batch upsert size | `500` |
| `GFX_SYNC_FLUSH_INTERVAL` | Batch flush interval (seconds) | `5.0` |
| `GFX_SYNC_HEALTH_PORT` | Health check HTTP port | `8080` |
| `GFX_SYNC_LOG_LEVEL` | Logging level | `INFO` |

## Key Design Decisions

- **httpx over supabase-py**: Direct HTTP for better control and async support
- **Polling over inotify**: Cross-platform NAS/SMB compatibility (watchdog + 2s polling)
- **SQLite offline queue**: WAL mode for concurrent read/write, resilient to network failures
- **Rate limit handling**: Exponential backoff with jitter (base 1s, max 5 retries)
- **file_hash as conflict key**: SHA-256 of file content for deduplication
