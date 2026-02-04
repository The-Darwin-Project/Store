# Darwin Store

A self-aware vulnerable application for Darwin demos. The Store reports its topology and metrics to the Darwin BlackBoard brain, and accepts chaos injection from the Chaos Controller.

## Architecture

```
┌─────────────────────────────────────────┐
│           Darwin Store Pod              │
│                                         │
│  ┌─────────────┐   ┌─────────────────┐  │
│  │ Store API   │   │ Chaos Controller│  │
│  │ :8080       │   │ :9000           │  │
│  │             │   │                 │  │
│  │ - Products  │   │ - CPU Attack    │  │
│  │ - Health    │   │ - Latency       │  │
│  │             │   │ - Errors        │  │
│  └──────┬──────┘   └────────┬────────┘  │
│         │                   │           │
│         └───────┬───────────┘           │
│                 │                       │
│         ┌───────▼───────┐               │
│         │ /tmp/chaos_   │               │
│         │  state.json   │               │
│         └───────────────┘               │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │     DarwinClient (Thread)       │    │
│  │  - Collects metrics (psutil)    │    │
│  │  - Discovers topology (env)     │    │
│  │  - Streams to BlackBoard        │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## Quick Start

### Local Development

```bash
# Install dependencies
cd Store
pip install -r requirements.txt

# Run Store API (port 8080)
uvicorn src.app.main:app --port 8080 &

# Run Chaos Controller (port 9000)
uvicorn src.chaos.main:app --port 9000 &

# Test health
curl http://localhost:8080/
# {"status":"store_online","service":"darwin-store","version":"1.0.0"}

# Test products
curl http://localhost:8080/products
# []

# Open Chaos UI
open http://localhost:9000/
```

### Helm Deployment (OpenShift)

```bash
# Install with defaults
helm install darwin-store ./helm

# Install with custom values
helm install darwin-store ./helm \
  --set darwin.url=http://my-blackboard:8000 \
  --set postgres.persistence.size=2Gi

# Disable persistence for quick PoC
helm install darwin-store ./helm \
  --set postgres.persistence.enabled=false

# Verify deployment
helm template ./helm
kubectl get pods -l app=darwin-store
```

## API Reference

### Store API (Port 8080)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/products` | GET | List all products |
| `/products/{id}` | GET | Get product by ID |
| `/products` | POST | Create product |
| `/products/{id}` | PUT | Update product |
| `/products/{id}` | DELETE | Delete product |

### Chaos API (Port 9000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Chaos UI |
| `/api/status` | GET | Current chaos state |
| `/api/attack/cpu` | POST | Toggle CPU burn |
| `/api/attack/latency?ms=500` | POST | Set latency (ms) |
| `/api/attack/errors?rate=0.5` | POST | Set error rate (0-1) |
| `/api/reset` | POST | Reset all chaos |

## Chaos Attacks

### CPU Attack
Starts a busy-loop thread that burns CPU cycles. The CPU usage is visible to the Darwin BlackBoard via telemetry.

```bash
curl -X POST http://localhost:9000/api/attack/cpu
# {"status":"cpu_attack_started","cpu_load":true}

# Toggle off
curl -X POST http://localhost:9000/api/attack/cpu
# {"status":"cpu_attack_stopped","cpu_load":false}
```

### Latency Injection
Adds artificial delay to all Store API requests.

```bash
curl -X POST "http://localhost:9000/api/attack/latency?ms=1000"
# {"status":"latency_set","latency_ms":1000}

# Verify (should take >1s)
time curl http://localhost:8080/products
```

### Error Injection
Returns HTTP 500 errors probabilistically.

```bash
curl -X POST "http://localhost:9000/api/attack/errors?rate=0.5"
# {"status":"error_rate_set","error_rate":0.5}

# 50% of requests will return 500
curl http://localhost:8080/products
# {"error": "Chaos injection - simulated failure"}
```

## Telemetry Schema

The Store pushes telemetry to Darwin BlackBoard every 5 seconds:

```json
{
  "service": "darwin-store",
  "version": "1.0.0",
  "metrics": {
    "cpu": 45.2,
    "memory": 62.1,
    "error_rate": 5.0
  },
  "topology": {
    "dependencies": [
      {
        "target": "postgres-db",
        "type": "db",
        "env_var": "DATABASE_URL"
      }
    ]
  }
}
```

**Important:** The `env_var` field contains the environment variable KEY name (not the value). This allows the Darwin SysAdmin Agent to construct `kubectl patch` commands.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVICE_NAME` | `darwin-store` | Service name in telemetry |
| `SERVICE_VERSION` | `1.0.0` | Service version in telemetry |
| `DARWIN_URL` | `http://darwin-blackboard:8000` | BlackBoard URL |
| `DATABASE_URL` | (none) | Postgres connection string |

### Helm Values

See `helm/values.yaml` for all configurable options:

- `image.*` - Container image settings
- `darwin.*` - BlackBoard connection
- `postgres.*` - Postgres StatefulSet settings
- `resources.*` - Resource limits
- `*SecurityContext` - Security settings

## Cross-Process State

The Store and Chaos Controller run as separate uvicorn processes in the same container. They share state via a file-backed JSON store at `/tmp/chaos_state.json` with `fcntl` file locking.

This is a PoC pattern. For production, use Redis or shared memory.
