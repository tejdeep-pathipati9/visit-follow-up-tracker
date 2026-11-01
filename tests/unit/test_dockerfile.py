"""The image must contain every file the application loads at run time."""

from pathlib import Path
import re

from app.ingestion.settings import DEFAULT_SETTINGS_PATH

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_copies_the_settings_file_to_where_the_app_looks_for_it():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    workdir = re.search(r"^WORKDIR\s+(\S+)", dockerfile, re.MULTILINE).group(1)
    relative = DEFAULT_SETTINGS_PATH.relative_to(PROJECT_ROOT)
    copies = [line.split()[1:] for line in dockerfile.splitlines() if line.startswith("COPY ")]

    assert any(
        source.rstrip("/") in (str(relative), str(relative.parent)) and destination.startswith(("./", workdir))
        for *sources, destination in copies
        for source in sources
    ), f"Dockerfile does not copy {relative} into {workdir}"


def test_settings_file_is_not_excluded_from_the_docker_build_context():
    ignored = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert "config" not in ignored and "config/" not in ignored
    assert "config/settings.json" not in ignored
