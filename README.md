# Stepik Autopilot MCP

## Running locally

Install the project with `uv sync --all-groups`, create `.env` from
`.env.example`, and fill in the Stepik OAuth credentials. Then start the
server over stdio:

```sh
uv run stepik-autopilot --transport stdio
```

For a local Streamable HTTP endpoint, bind explicitly to loopback:

```sh
uv run stepik-autopilot --transport http --host 127.0.0.1 --port 8000
```

The first startup creates the SQLite Core schema. Submission and explicit
lecture-view operations use the Stepik REST resource envelopes directly.

To scope a plan or run by the one-based section numbers shown in the Stepik
course outline, use `selection="explicit"` with `section_numbers`. The server
resolves the corresponding section, unit, assignment, and step identifiers
through its authenticated Stepik client, so the MCP client does not need a
separate browser or `curl` request. For example:

```json
{
  "arguments": {
    "course_id": "68343",
    "selection": "explicit",
    "section_numbers": [1, 2, 4]
  }
}
```

`stepik_plan` returns the resolved section title, `section_id`, and `step_ids`.
Pass the same `section_numbers` to `stepik_run_start`. `section_numbers` and
`explicit_step_ids` are alternative scopes and cannot be combined.

## Connecting to Codex

Register the local stdio server, replacing both absolute paths below with
your installation paths (`command -v uv` prints the path to uv):

```sh
codex mcp add stepik-autopilot -- /absolute/path/to/uv \
  --directory /absolute/path/to/stepik-autopilot \
  run --locked stepik-autopilot --transport stdio
```

`--directory` ensures that the server reads this project's `.env` and uses
its configured SQLite database even when Codex is opened in another folder.
Credentials stay in `.env`; they do not need to be copied into Codex config.
Verify the registration with `codex mcp get stepik-autopilot` and restart
Codex to load the server.
