"""Verify initial schema creation against disposable SQLite databases."""

from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.table_generate import table_generate


class TableGenerateTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db_path = Path(self.directory.name).resolve() / "nested" / "followups.db"

    def test_creates_tables_indexes_and_preserves_existing_data(self):
        self.assertEqual(table_generate(self.db_path), self.db_path)
        with closing(sqlite3.connect(self.db_path)) as connection:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertEqual(
                tables, {"patients", "staff", "episodes", "visits", "followups"}
            )
            indexes = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }
            self.assertTrue({
                "idx_visits_episode_date", "idx_visits_patient_date",
                "idx_followups_status_due", "idx_followups_staff_status",
            }.issubset(indexes))
            connection.execute(
                "INSERT INTO patients (patient_id, name) VALUES (?, ?)",
                ("P001", "Synthetic Patient"),
            )
            connection.commit()

        table_generate(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT name FROM patients").fetchall(),
                [("Synthetic Patient",)],
            )
            self.assertEqual(
                connection.execute("PRAGMA integrity_check").fetchone(), ("ok",)
            )

    def test_environment_path_and_explicit_override(self):
        other_path = Path(self.directory.name).resolve() / "other.db"
        with patch.dict("os.environ", {"FOLLOWUP_DB_PATH": str(self.db_path)}):
            self.assertEqual(table_generate(), self.db_path)
            self.assertEqual(table_generate(other_path), other_path)

    def test_failed_schema_rolls_back_created_tables(self):
        schema_path = Path(self.directory.name) / "invalid.sql"
        schema_path.write_text(
            "CREATE TABLE temporary_table (id TEXT);\nINVALID SQL;",
            encoding="utf-8",
        )
        with patch("scripts.table_generate.SCHEMA_PATH", schema_path):
            with self.assertRaises(sqlite3.Error):
                table_generate(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall(),
                [],
            )


if __name__ == "__main__":
    unittest.main()
