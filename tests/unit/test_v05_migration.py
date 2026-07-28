import sqlite3

from src.storage.v05_migration import add_v05_schema


def test_v05_schema_defines_material_tables_constraints_and_indexes() -> None:
    with sqlite3.connect(":memory:") as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE job_snapshots (id INTEGER PRIMARY KEY, job_id TEXT)"
        )

        add_v05_schema(conn)

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        package_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(material_packages)")
        }

    assert {
        "material_tasks",
        "material_packages",
        "material_review_events",
    } <= tables
    assert {
        "payload_json",
        "review_status",
        "is_current_approved",
    } <= package_columns
    assert {
        "idx_material_tasks_batch",
        "idx_material_tasks_job_status",
        "idx_material_packages_job_version",
        "idx_material_one_current_approved",
        "idx_material_review_package",
    } <= indexes
