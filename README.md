# LeaveManager MCP Server

A small [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that lets an AI assistant (like Claude) check employee leave balances, apply for and cancel leave, and view leave history...

It is built with the official MCP Python SDK (`FastMCP`) and stores its data in a local JSON file, so it's a demo or learning project, not a production HR system.

## Features

| Type     | Name                            | What it does                                                         |
| -------- | ------------------------------- | -------------------------------------------------------------------- |
| Tool     | `get_leave_balance`             | Returns how many leave days an employee has left.                     |
| Tool     | `apply_leave`                   | Applies leave for a list of dates and deducts them from the balance.  |
| Tool     | `cancel_leave`                  | Cancels booked dates and refunds the days.                            |
| Tool     | `get_leave_history`             | Lists every date the employee has booked.                             |
| Tool     | `add_employee`                  | Adds a new employee with a starting balance.                          |
| Tool     | `check_availability`            | Checks dates without booking them, with a reason per date.            |
| Tool     | `draft_handover_note`           | Asks **your** model to write a handover note (MCP sampling).          |
| Resource | `leave://employees`             | Every employee with their current balance, as JSON.                   |
| Resource | `leave://{employee_id}/balance` | One employee's balance and booked dates, as JSON.                     |
| Resource | `greeting://{name}`             | Returns a personalized greeting message.                              |
| Prompt   | `leave_request_email`           | Template that drafts a leave request email for given dates.           |

Tools return **structured JSON** (each has an output schema), not sentences. Invalid input raises an error, so the client sees a real tool error instead of a string that looks like success.

### How the code is organised

The package lives under `src/`, which keeps the installed code separate from the tests and project files.

| Module       | Job                                                                 |
| ------------ | ------------------------------------------------------------------- |
| `config.py`  | Settings, read from the environment in one place.                    |
| `models.py`  | The shapes the tools return.                                         |
| `storage.py` | `LeaveStore`: reading and writing the JSON data file.                |
| `rules.py`   | Date checks, with `today` injectable so tests don't depend on the clock. |
| `service.py` | `LeaveService`: the leave rules. No MCP in sight.                    |
| `server.py`  | `create_server(service)`: the MCP layer.                             |
| `__main__.py`| Wires it together and serves over stdio.                             |

Nothing is a module-level global. `create_server` is handed a service, and the service is handed a store, so a test can build the whole stack on a temporary file and get a server identical to the real one.

### What `Context` does

Every tool takes a `ctx: Context` argument. MCP fills it in, and it never appears in the tool's input schema. It is how a tool talks back to the client *while it is running*:

- `await ctx.info(...)` / `ctx.debug(...)` — log messages the client can show
- `await ctx.report_progress(progress, total, message)` — drives a progress bar; `apply_leave` reports two steps
- `await ctx.session.create_message(...)` — **sampling**: the tool asks the client's own model a question. `draft_handover_note` uses this, which is why this server needs no API key of its own. A client that doesn't support sampling gets a clear error instead of a crash.

### Sample data

A fresh server (no `leave_data.json` yet) starts with two employees:

| Employee ID | Balance | History                    |
| ----------- | ------- | -------------------------- |
| `E001`      | 18      | `2024-12-25`, `2025-01-01` |
| `E002`      | 20      | *(none)*                   |

---

## Requirements

- Python **3.10+**
- The MCP Python SDK **v1.x**: `mcp[cli]<2`

> [!IMPORTANT]
> Pin `mcp` below version 2. In `mcp` 2.x, `FastMCP` was renamed to `MCPServer`, so `from mcp.server.fastmcp import FastMCP` fails with `ModuleNotFoundError`. This server was tested with `mcp` **1.30.0**.

---

## Installation

```bash
cd MCP-Server-Leave-Management-System

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install the package and its test dependencies
pip install -e ".[dev]"
```

`-e` installs it in editable mode, so your edits take effect without reinstalling.

---

## Running the server

```bash
leave-manager              # the installed command
python -m leave_manager    # or run the package directly
```

The server uses the **stdio** transport (the default for `mcp.run()`). When it starts, it waits quietly for an MCP client on stdin/stdout. Logs go to **stderr**, never stdout, because stdout carries the MCP protocol messages.

### Configuration

| Environment variable    | Default                            | What it does                               |
| ----------------------- | ---------------------------------- | ------------------------------------------ |
| `LEAVE_DATA_FILE`       | `~/.leave_manager/leave_data.json` | Where leave data is saved between runs.    |
| `LEAVE_LOG_LEVEL`       | `INFO`                             | Python log level, e.g. `DEBUG`, `WARNING`. |
| `LEAVE_DEFAULT_BALANCE` | `20`                               | Starting balance for a new employee.       |

The data file lives in your home folder by default, so it doesn't depend on which directory you start the server from. Missing folders are created on first save.

### Testing with MCP Inspector

```bash
mcp dev src/leave_manager/__main__.py
```

> `mcp dev` requires [`uv`](https://docs.astral.sh/uv/) and Node.js (`npx`) to be installed.

---

## Running the tests

```bash
pytest -q
```

48 tests, in four files:

| File               | Covers                                                                   |
| ------------------ | ------------------------------------------------------------------------ |
| `test_rules.py`    | Date parsing and validation, with the clock pinned.                       |
| `test_config.py`   | Settings defaults and environment overrides.                              |
| `test_service.py`  | The leave rules, the refund path, and data surviving a restart.           |
| `test_server.py`   | The protocol layer: schemas, tool errors, progress, logging, sampling.    |

Fixtures in `conftest.py` give each test its own store on a temporary file, so the tests never touch real data and never need to reload modules. Sampling is tested with a fake model, so no API calls are made.

---

## Connecting to Claude Desktop

Open your Claude Desktop config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add this, using the **absolute paths** on your machine:

```json
{
  "mcpServers": {
    "LeaveManager": {
      "command": "/ABSOLUTE/PATH/TO/MCP-Server-Leave-Management-System/venv/bin/leave-manager"
    }
  }
}
```

> If you connected this server before, the old config pointed at `main.py`, which no longer exists. Replace it with the block above.

Restart Claude Desktop. The LeaveManager tools should then show up in the tools menu.

> If you have `uv` installed, you can instead run `mcp install main.py`, which writes this config for you.

---

## Tool reference

### `get_leave_balance`

| Parameter     | Type     | Required |
| ------------- | -------- | -------- |
| `employee_id` | `string` | Yes      |

```json
{ "employee_id": "E001", "balance": 18, "days_taken": 2 }
```

---

### `apply_leave`

Apply leave for specific dates. Each date counts as **one day**.

| Parameter     | Type              | Required |
| ------------- | ----------------- | -------- |
| `employee_id` | `string`          | Yes      |
| `leave_dates` | `array of string` | Yes      |

Each date must be in `YYYY-MM-DD` format, must not be in the past, and can't be repeated in the same request or already booked.

```json
{
  "employee_id": "E002",
  "dates_applied": ["2026-12-01", "2026-12-02"],
  "days_used": 2,
  "remaining_balance": 18
}
```

---

### `cancel_leave`

Cancel dates the employee already booked and refund the days.

| Parameter     | Type              | Required |
| ------------- | ----------------- | -------- |
| `employee_id` | `string`          | Yes      |
| `leave_dates` | `array of string` | Yes      |

```json
{
  "employee_id": "E002",
  "dates_cancelled": ["2026-12-01"],
  "days_refunded": 1,
  "remaining_balance": 19
}
```

---

### `get_leave_history`

| Parameter     | Type     | Required |
| ------------- | -------- | -------- |
| `employee_id` | `string` | Yes      |

```json
{ "employee_id": "E001", "dates": ["2024-12-25", "2025-01-01"], "days_taken": 2 }
```

---

### `add_employee`

| Parameter     | Type      | Required | Default |
| ------------- | --------- | -------- | ------- |
| `employee_id` | `string`  | Yes      | —       |
| `balance`     | `integer` | No       | `20`    |

```json
{ "employee_id": "E003", "balance": 20, "days_taken": 0 }
```

---

### `draft_handover_note`

Asks the client's model to draft a handover note for the employee's booked leave. Returns plain text. Errors if the employee has no booked leave, or if the client doesn't support sampling.

| Parameter     | Type     | Required |
| ------------- | -------- | -------- |
| `employee_id` | `string` | Yes      |

---

### `check_availability`

Check dates **without** booking them. Useful before `apply_leave`.

| Parameter     | Type              | Required |
| ------------- | ----------------- | -------- |
| `employee_id` | `string`          | Yes      |
| `leave_dates` | `array of string` | Yes      |

```json
{
  "employee_id": "E002",
  "dates": [
    { "leave_date": "2026-12-01", "available": false, "reason": "Leave is already booked on this date." },
    { "leave_date": "2026-12-11", "available": true,  "reason": "Available." }
  ],
  "all_available": false
}
```

---

## Errors

Bad input raises a tool error (the client sees `isError: true`) with a message such as:

```text
Employee 'E999' not found.
Give at least one date.
Invalid date 'hello'. Use the format YYYY-MM-DD.
Cannot apply leave for a past date: 2020-01-01.
Duplicate dates in your request. List each date once.
Leave already applied for: 2026-12-01.
Insufficient leave balance. You requested 24 day(s) but have only 20.
No leave booked on: 2026-12-10.
Employee 'E001' already exists.
```

---

## Example prompts

Once the server is connected, try asking Claude:

- "How many leave days does E001 have left?"
- "Is E002 free on 2026-12-01 and 2026-12-02?"
- "Apply leave for E002 on 2026-12-01 and 2026-12-02."
- "Cancel E002's leave on 2026-12-01."
- "Add a new employee E003 with 15 days."
- "Draft a leave request email for E001 for 2026-12-24."
- "Write a handover note for E001's leave."

---

## Limitations

These are known limitations of the current code:

- **No authentication.** Any connected client can view or change any employee's leave.
- **Single file storage.** Data is a JSON file read into memory, with no locking, so two servers sharing one file would overwrite each other. SQLite would be the next step.
- **No half days or date ranges.** Every date is one full day and must be listed individually.
- **No holidays or weekends.** Any future date can be booked, including a Sunday.
  
## Project structure

```text
MCP-Server-Leave-Management-System/
├── src/
│   └── leave_manager/
│       ├── __init__.py
│       ├── __main__.py      # entry point
│       ├── config.py        # settings from the environment
│       ├── models.py        # what the tools return
│       ├── rules.py         # date checks
│       ├── service.py       # the leave rules
│       ├── server.py        # the MCP layer
│       └── storage.py       # the JSON data file
├── tests/
│   ├── conftest.py          # shared fixtures
│   ├── test_config.py
│   ├── test_rules.py
│   ├── test_server.py
│   └── test_service.py
├── pyproject.toml           # dependencies, entry point, pytest config
├── .gitignore
└── README.md
```
