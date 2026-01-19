# GFX Sync Agent

NAS JSON to Supabase sync agent for PokerGFX data.

## Overview

GFX Sync Agent monitors NAS directories for PokerGFX JSON files and synchronizes them to Supabase cloud in normalized format.

## Features

- Real-time file monitoring (watchdog, 2s polling)
- Batch processing (500 records / 5 seconds)
- Offline queue with automatic retry (SQLite)
- Dead letter queue for failed records
- Multi-PC support via registry

## Requirements

- Python 3.11+
- Docker (for NAS deployment)

## Quick Start

```bash
# Development
pip install -e ".[dev]"
python -m src.sync_agent.main_v3

# Docker
docker compose up -d
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GFX_SYNC_SUPABASE_URL` | Supabase project URL | Required |
| `GFX_SYNC_SUPABASE_SECRET_KEY` | Supabase service_role key | Required |
| `GFX_SYNC_NAS_BASE_PATH` | NAS mount path | `/app/data` |
| `GFX_SYNC_POLL_INTERVAL` | File polling interval (seconds) | `2.0` |
| `GFX_SYNC_BATCH_SIZE` | Batch size for upserts | `500` |

## Architecture

```
NAS Storage → Docker Agent → Supabase Cloud
   (JSON)      (Python)       (PostgreSQL)
```

## License

Private - All rights reserved.
