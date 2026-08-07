# 🎫 AI Support Portal — Lakebase-Powered Databricks App

An internal support ticketing system built with **Streamlit** and deployed as a **Databricks App**, backed by **Lakebase** (Databricks' managed Postgres for operational/transactional workloads).

**Live app:** [supportapps-7474659512156367.aws.databricksapps.com](https://supportapps-7474659512156367.aws.databricksapps.com)

> Access is restricted to users with permission on the Databricks workspace. Databricks Apps do not support public/anonymous access — see [Authentication](#authentication) below.

---

## Overview

This app lets support agents:

- View all support tickets, with filtering by status
- Select a ticket to see its full message history
- Create a new ticket (with category, priority, and an initial message)
- Add follow-up messages to an existing ticket
- Update a ticket's status (`Open`, `In Progress`, `Resolved`)
- View aggregate statistics (totals by status, category, and priority)

All data is read from and written to Lakebase in real time — nothing is hardcoded.

---

## Tech stack

| Layer | Technology |
|---|---|
| UI | [Streamlit](https://streamlit.io/) |
| Hosting | [Databricks Apps](https://docs.databricks.com/en/dev-tools/databricks-apps/) |
| Database | [Lakebase](https://docs.databricks.com/en/oltp/) (managed Postgres, OLTP) |
| DB driver | `psycopg2` |
| Auth | Databricks OAuth via the app's service principal (`databricks-sdk`) |

---

## Database schema

Two related tables in the `support_app` schema:

**`tickets`**

| Column | Description |
|---|---|
| `ticket_id` | Primary key |
| `title` | Ticket title |
| `status` | `Open` \| `In Progress` \| `Resolved` |
| `created_by` | Requester name/e-mail |
| `priority` | `Low` \| `Medium` \| `High` \| `Critical` |
| `category` | Ticket category |
| `created_at` | Timestamp |

**`ticket_messages`**

| Column | Description |
|---|---|
| `message_id` | Primary key |
| `ticket_id` | Foreign key → `tickets.ticket_id` |
| `message_text` | Message body |
| `author` | Message author |
| `created_at` | Timestamp |

---

## Authentication

This app **does not store any password, token, or credential in code or configuration files**. Instead:

1. Lakebase is added as a **resource** to the Databricks App, which injects `PGHOST` and `PGUSER` as environment variables automatically.
2. The app authenticates to Postgres using a short-lived **OAuth token**, generated at runtime via `databricks.sdk.core.Config().oauth_token()`, using the app's own service principal identity.
3. Database-level permissions are granted directly to the service principal (`DATABRICKS_CLIENT_ID`) via `GRANT` statements in the Lakebase SQL Editor — no static credentials are ever created or shared.

```python
from databricks.sdk.core import Config

def get_db_connection():
    cfg = Config()
    return psycopg2.connect(
        host=os.environ["PGHOST"],
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "databricks_postgres"),
        user=os.environ["PGUSER"],
        password=cfg.oauth_token().access_token,
        sslmode="require",
        options="-c search_path=support_app,public",
    )
```

Because Databricks Apps don't support public/anonymous access, anyone using this app needs a recognized account in the associated Databricks workspace with **CAN USE** permission on the app.

---

## Project structure

```
.
├── src/
│   └── app.py          # Streamlit application
├── app.yaml             # Databricks App run configuration
├── requirements.txt      # Python dependencies
└── README.md
```

---

## Deployment

1. Create a Lakebase project (branch + database) in your Databricks workspace.
2. Create the `support_app` schema and tables above (see `tickets` / `ticket_messages` DDL).
3. Create the Databricks App and connect it to your GitHub repository.
4. In the app's **Resources** tab, add the Lakebase project/branch/database as a resource — this injects `PGHOST`/`PGUSER` automatically.
5. In the **Lakebase SQL Editor**, grant the app's service principal (`DATABRICKS_CLIENT_ID`, found in the app's **Environment** tab) access to the schema:
   ```sql
   GRANT USAGE ON SCHEMA support_app TO "<DATABRICKS_CLIENT_ID>";
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA support_app TO "<DATABRICKS_CLIENT_ID>";
   ```
6. Deploy the app from the Databricks UI.

`app.yaml`:
```yaml
command: ['streamlit', 'run', 'src/app.py']
```

---

## Local development

Local runs authenticate with **your own** Databricks identity (via `databricks auth login`), not the app's service principal — your user must also have `GRANT` access to the `support_app` schema.

```bash
pip install -r requirements.txt
export PGHOST=<your-lakebase-host>
export PGUSER=<your-user-or-service-principal>
export PGDATABASE=databricks_postgres
streamlit run src/app.py
```

---

## Roadmap

- [ ] Delete ticket functionality with a confirmation step
- [ ] Stronger input validation with field-level error messages
- [ ] Ticket assignment (assignee field) and "my tickets" filtering

---

## Reflection

**Most difficult part:** Handling stale-session errors that appeared after the app had been open for a long time, which required redeploying to resolve.

**Lakebase vs. a traditional analytics table:** Lakebase (Postgres) is built for low-latency, row-level OLTP operations — creating a ticket, updating a status, reading one record — with ACID transactions. A traditional analytics table (e.g. Delta) is optimized for reading and aggregating large volumes of data at once via batch writes, not for fast, per-row, concurrent read/write operations from a live application.

**Next feature:** Delete functionality for tickets, with a confirmation step to prevent accidental data loss.
