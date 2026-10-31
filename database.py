"""
database.py : everything that touches the database lives here.

Two databases are supported, and the code picks one by itself:

  * ONLINE (Neon):  if an environment variable called DATABASE_URL exists, we use Postgres.
                    This is the one that keeps your data safe on the internet.
  * ON YOUR LAPTOP: if DATABASE_URL does not exist, we use SQLite, which is just ONE FILE
                    (submissions.db) next to your code.  Nothing to install.
"""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# The address of the online database (you will paste it into Render, never into the code).
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)

# Where the SQLite file lives when we are on your laptop.
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "submissions.db"))

if USE_POSTGRES:
    import psycopg                      # the library that talks to Postgres
    from psycopg.rows import dict_row   # lets us read columns by name, like row["age"]

# SQLite writes the placeholder as ?   Postgres writes it as %s   (same job: "a value goes here")
PLACEHOLDER = "%s" if USE_POSTGRES else "?"


def connect():
    """Open a connection to whichever database we are using."""
    if USE_POSTGRES:
        # connect_timeout: Neon sleeps when nobody visits, so the first connection can be slow.
        return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=20)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the table if it does not exist yet.  Safe to run every time the server starts."""
    # The only difference between the two databases here is how the id number is made.
    id_column = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

    # closing(...) makes sure the connection is closed when the block ends.
    # `with conn:` inside means: save (commit) if everything worked, undo (rollback) if an error happened.
    with closing(connect()) as conn, conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS submissions (
                id                   {id_column},
                created_at           TEXT             NOT NULL,
                codename             TEXT             NOT NULL,
                age                  INTEGER          NOT NULL,
                employment_status    TEXT             NOT NULL,
                relationship_status  TEXT             NOT NULL,
                monthly_income       DOUBLE PRECISION NOT NULL,
                m1_spending          DOUBLE PRECISION NOT NULL,   -- last month
                m1_emergency         DOUBLE PRECISION NOT NULL,
                m2_spending          DOUBLE PRECISION,            -- two months ago (can be empty = NULL)
                m2_emergency         DOUBLE PRECISION,
                m3_spending          DOUBLE PRECISION,            -- three months ago (can be empty = NULL)
                m3_emergency         DOUBLE PRECISION,
                predicted_next_month DOUBLE PRECISION NOT NULL,   -- what the model said at the time
                model_version        INTEGER          NOT NULL
            )
            """
        )


def save_submission(data: dict) -> int:
    """Insert one person's answers.  `data` is a dictionary whose keys match the columns below."""
    columns = [
        "codename", "age", "employment_status", "relationship_status", "monthly_income",
        "m1_spending", "m1_emergency", "m2_spending", "m2_emergency",
        "m3_spending", "m3_emergency", "predicted_next_month", "model_version",
    ]
    values = [data[c] for c in columns]
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # The placeholders stand for the values.  NEVER paste user text straight into an SQL string:
    # that is how "SQL injection" attacks work.  With placeholders the database treats the value
    # as plain data, whatever it contains.
    marks = ", ".join(PLACEHOLDER for _ in range(len(columns) + 1))
    sql = f"INSERT INTO submissions (created_at, {', '.join(columns)}) VALUES ({marks})"

    with closing(connect()) as conn, conn:
        if USE_POSTGRES:
            # Postgres has no "lastrowid", so we ask it to hand the new id back.
            row = conn.execute(sql + " RETURNING id", [created_at] + values).fetchone()
            return int(row["id"])
        cursor = conn.execute(sql, [created_at] + values)
        return cursor.lastrowid


def count_people() -> int:
    """How many DIFFERENT code names have submitted."""
    with closing(connect()) as conn:
        row = conn.execute("SELECT COUNT(DISTINCT codename) AS n FROM submissions").fetchone()
        return int(row["n"])