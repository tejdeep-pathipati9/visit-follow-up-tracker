"""The first manager comes from a script, because only a manager can add staff in the app."""

from contextlib import closing
import sqlite3

import pytest

from scripts.create_manager import create_manager, main
from scripts.table_generate import table_generate


@pytest.fixture
def database(tmp_path):
    return table_generate(tmp_path / "followups.db")


def staff(database):
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute("SELECT staff_id, name, role, email FROM staff ORDER BY staff_id").fetchall()


def test_adds_a_manager_who_can_sign_in(database):
    assert create_manager(" Clinic Manager ", " Manager@Clinic.Example ", database) == "M001"
    assert staff(database) == [("M001", "Clinic Manager", "manager", "manager@clinic.example")]


def test_manager_ids_never_clash_with_imported_staff(database):
    # An import file numbers its staff S001 and up; managers added here are M-numbered.
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("INSERT INTO staff (staff_id, name, role) VALUES ('S007', 'Dr. Example', 'doctor')")
        connection.execute("INSERT INTO staff (staff_id, name, role) VALUES ('M002', 'Manager Example', 'manager')")
    assert create_manager("Clinic Manager", "manager@clinic.example", database) == "M003"


@pytest.mark.parametrize(("name", "email", "message"), [
    ("", "manager@clinic.example", "name"),
    ("Clinic Manager", "not-an-email", "email"),
])
def test_bad_input_is_rejected(database, name, email, message):
    with pytest.raises(ValueError, match=message):
        create_manager(name, email, database)
    assert staff(database) == []


def test_an_email_in_use_is_rejected(database):
    create_manager("Clinic Manager", "manager@clinic.example", database)
    with pytest.raises(ValueError, match="already signs in"):
        create_manager("Second Manager", "MANAGER@clinic.example", database)


def test_missing_database_is_not_created(tmp_path):
    missing = tmp_path / "missing.db"
    with pytest.raises(ValueError, match="table_generate"):
        create_manager("Clinic Manager", "manager@clinic.example", missing)
    assert not missing.exists()


def test_command_line(database, capsys):
    main(["--name", "Clinic Manager", "--email", "manager@clinic.example", "--db-path", str(database)])
    assert "sign in with manager@clinic.example" in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        main(["--name", "Again", "--email", "manager@clinic.example", "--db-path", str(database)])
    assert error.value.code == 1
