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

## Architecture

```
NAS Storage → Polling Watcher → SyncService → Supabase Cloud
   (JSON)       (watchdog)        (httpx)       (PostgreSQL)
```

### Core Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `SyncAgent` | `src/sync_agent/core/agent.py` | Main orchestrator - 4 parallel tasks |
| `SyncService` | `src/sync_agent/core/sync_service_v3.py` | Sync logic (realtime + batch) |
| `PollingWatcher` | `src/sync_agent/watcher/polling_watcher.py` | File change detection |
| `BatchQueue` | `src/sync_agent/queues/batch_queue.py` | In-memory batch (500/5s) |
| `OfflineQueue` | `src/sync_agent/queues/offline_queue.py` | SQLite failover queue |
| `SupabaseClient` | `src/sync_agent/db/supabase_client.py` | httpx-based Supabase client |
| `Settings` | `src/sync_agent/config/settings.py` | pydantic-settings config |

### Data Flow

1. **Created files** → Immediate single upsert
2. **Modified files** → BatchQueue → Batch upsert (500 records / 5 seconds)
3. **Network failure** → OfflineQueue (SQLite) → Periodic retry (60s)

### Dashboard (Next.js)

Located in `dashboard/` - separate Next.js 14 app with Tailwind CSS for monitoring.

```bash
cd dashboard
npm install
npm run dev
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GFX_SYNC_SUPABASE_URL` | Supabase project URL |
| `GFX_SYNC_SUPABASE_SECRET_KEY` | Supabase service_role key |
| `GFX_SYNC_NAS_BASE_PATH` | NAS mount path (default: `/app/data`) |
| `GFX_SYNC_POLL_INTERVAL` | File polling interval in seconds (default: `2.0`) |
| `GFX_SYNC_BATCH_SIZE` | Batch size for upserts (default: `500`) |

## Key Design Decisions

- **httpx over supabase-py**: Direct HTTP for better control and async support
- **Polling over inotify**: Cross-platform NAS compatibility (watchdog + 2s polling)
- **SQLite offline queue**: Resilient to network failures with automatic retry
- **Rate limit handling**: Exponential backoff with jitter
