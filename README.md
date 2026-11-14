# bleep-demo-app

A small web app with switchable faults, made as a demo target for
[Bleep](https://github.com/DannyKuk/bleep), an on-call agent for Docker hosts. Bleep watches it,
opens an incident when it breaks, investigates from the logs and this README, proposes a fix and
verifies it.

It is one container: Python with FastAPI, serving one HTML page and a `/health` URL. No database,
no build step. The page shows the app's state and has four buttons that break it on purpose.

## Run it locally

```sh
docker build -t bleep-demo-app .
docker run --rm -p 3000:3000 -e DEMO_PASSWORD=change-me bleep-demo-app
```

Open http://localhost:3000. Without Docker: `uv run python -m demo_app`.
Tests: `uv run pytest`.

## Settings

Set as environment variables. Defaults and safe values:

| Variable | Default | Safe value | What it does |
| --- | --- | --- | --- |
| `PORT` | `3000` | `3000` | Port the app listens on. |
| `HOST` | `0.0.0.0` | `0.0.0.0` | Address the app binds. `0.0.0.0` accepts connections from outside the container, which a reverse proxy needs. |
| `FAIL_AFTER_S` | unset | unset, empty or `0` | Seconds after startup when the app turns unhealthy. Unset, empty or `0` means never. |
| `DEMO_PASSWORD` | unset | any non-empty value | Password for the fault buttons. Unset disables them. |

The startup log says where the app listens, for example `listening on 0.0.0.0:3000`.

### `HOST`

`HOST=127.0.0.1` binds the loopback interface only. The app still runs and its own health check
inside the container passes, but nothing outside the container can reach it, so a reverse proxy in
front of it answers 502. The log shows `listening on 127.0.0.1:3000`.

To fix: set `HOST` to `0.0.0.0` (or remove it) and redeploy.

### `FAIL_AFTER_S`

With `FAIL_AFTER_S=60` the app is healthy for 60 seconds after startup, then `/health` answers
500 and the log repeats `FAIL_AFTER_S=60 elapsed, marking the service unhealthy`.

To fix: set `FAIL_AFTER_S` to empty or `0` (or remove it) and redeploy. A restart alone does not
help, the timer starts again.

### `DEMO_PASSWORD`

The fault buttons ask for this password, which is checked on the server with each request. The
page and `/health` stay public. If it is not set the buttons are disabled and the page says so.

## Faults

The four buttons on the page break the app until it restarts. Each leaves a trace in the log.

| Button | What happens | Log | Fix |
| --- | --- | --- | --- |
| Hang | The process blocks. `/health` and the page stop answering. | `session sync: waiting for lock held by worker 3` | Restart the container. |
| Error state | `/health` answers 500. | `cache connection pool exhausted (0/20 connections available)`, repeated | Restart the container. |
| Memory leak | Memory grows by 8 MB a second until Docker kills the container for running out of memory. | `report cache holds N entries (M MB), no eviction` | Restart the container (it restarts on its own if the restart policy allows). |
| Crash | The process exits with code 1. | `unhandled error in session refresh, shutting down` and a stack trace | Restart the container. |

The memory leak only ends in a kill if the container has a memory limit; see below. Without a
limit it keeps growing until the host runs out of memory, so always set one.

Restarting clears all four. The two settings above are different: they come back after a restart
until the setting is changed and the app is redeployed.

## Deploy on Coolify

1. New resource from this repository with the **Dockerfile** build pack.
2. Port: `3000`. Health check path: `/health`.
3. Resource limits: memory limit of `256 MB`, so the memory leak ends in an out-of-memory kill.
4. Environment variables: set `DEMO_PASSWORD`. Leave `HOST` and `FAIL_AFTER_S` unset.
5. Deploy.

## Endpoints

| Path | |
| --- | --- |
| `GET /` | The page. |
| `GET /health` | `200 {"status":"ok"}` when healthy, `500 {"status":"error"}` when not. |
| `GET /api/status` | Uptime, health and which settings are active, as JSON. |
| `POST /api/faults/{hang,error,leak,crash}` | Trigger a fault. Body: `{"password": "..."}`. |
