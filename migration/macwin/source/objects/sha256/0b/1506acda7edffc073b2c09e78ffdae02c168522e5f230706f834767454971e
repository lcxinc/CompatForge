import json
import sqlite3
import ssl
import sys

import cryptography
import flask
import psycopg
from psycopg import pq


database_path = sys.argv[1]
result_path = sys.argv[2]

database = sqlite3.connect(database_path)
database.execute("PRAGMA journal_mode=WAL")
database.executescript(
    """
    DROP TABLE IF EXISTS compatibility_results;
    CREATE TABLE compatibility_results (
        id INTEGER PRIMARY KEY,
        component TEXT NOT NULL,
        category TEXT NOT NULL,
        score REAL NOT NULL
    );
    """
)
with database:
    database.executemany(
        "INSERT INTO compatibility_results(component, category, score) VALUES (?, ?, ?)",
        [
            ("pgAdmin Python", "\u4e2d\u6587\u6570\u636e", 98.0),
            ("psycopg", "PostgreSQL \u9a71\u52a8", 97.0),
        ],
    )
rows = database.execute(
    "SELECT component, category, printf('%.1f', score) "
    "FROM compatibility_results ORDER BY id"
).fetchall()
integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
database.close()

application = flask.Flask("macwin-pgadmin-probe")


@application.get("/health")
def health():
    return {"status": "ok", "message": "\u540e\u7aef\u670d\u52a1\u6b63\u5e38"}


with application.test_client() as client:
    response = client.get("/health")
    flask_probe = response.get_json()
    if response.status_code != 200 or flask_probe.get("status") != "ok":
        raise SystemExit(1)

result = {
    "pythonVersion": sys.version.split()[0],
    "sqliteVersion": sqlite3.sqlite_version,
    "opensslVersion": ssl.OPENSSL_VERSION,
    "cryptographyVersion": cryptography.__version__,
    "psycopgVersion": psycopg.__version__,
    "libpqVersion": pq.version(),
    "integrity": integrity,
    "rows": rows,
    "flaskProbe": flask_probe,
}
if len(sys.argv) >= 5:
    postgres_host = sys.argv[3]
    postgres_user = sys.argv[4]
    connection = psycopg.connect(
        host=postgres_host,
        port=5432,
        dbname="postgres",
        user=postgres_user,
        connect_timeout=5,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE TEMP TABLE macwin_pgadmin_probe "
            "(component text NOT NULL, category text NOT NULL, score numeric NOT NULL)"
        )
        cursor.executemany(
            "INSERT INTO macwin_pgadmin_probe(component, category, score) VALUES (%s, %s, %s)",
            [
                ("pgAdmin psycopg", "\u4e2d\u6587 PostgreSQL", 99.0),
                ("MacWin TCP", "\u6570\u636e\u5e93\u8fde\u63a5", 98.0),
            ],
        )
        cursor.execute(
            "SELECT component, category, to_char(score, 'FM9990.0') "
            "FROM macwin_pgadmin_probe ORDER BY component"
        )
        result["postgresRows"] = cursor.fetchall()
    connection.rollback()
    connection.close()

with open(result_path, "w", encoding="utf-8") as result_file:
    json.dump(result, result_file, ensure_ascii=False, indent=2)
    result_file.write("\n")
