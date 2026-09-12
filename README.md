# Stepik Autopilot MCP

## Running locally

Create `.env` from `.env.example`, then start the server over stdio:

```sh
uv run stepik-autopilot --transport stdio
```

For a local Streamable HTTP endpoint, bind explicitly to loopback:

```sh
uv run stepik-autopilot --transport http --host 127.0.0.1 --port 8000
```

The first startup creates the SQLite Core schema. Submission and explicit
lecture-view operations use the Stepik REST resource envelopes directly.
