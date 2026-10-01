"""Tests for the idempotent CSV import against the real messy seed file."""

from __future__ import annotations

import io
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.routers.episodes import import_csv_bytes

SEED_CSV = Path(
    os.environ.get("SEED_CSV_PATH", Path(__file__).resolve().parents[2] / "seed" / "episodes.csv")
)


def _upload(client: TestClient, headers: dict, content: bytes):
    return client.post(
        "/episodes/import",
        files={"file": ("episodes.csv", io.BytesIO(content), "text/csv")},
        headers=headers,
    )


def test_import_of_messy_seed_file_reports_clearly(client, login):
    headers = login("ops1@example.com")
    content = SEED_CSV.read_bytes()

    first = _upload(client, headers, content)
    assert first.status_code == 200, first.text
    report = first.json()
    assert report["rows_seen"] > 150
    assert report["imported"] + report["updated"] + report["skipped"] == report["rows_seen"]
    assert report["skipped"] > 0
    skipped_reasons = " | ".join(r["reason"] or "" for r in report["rows"] if r["action"] == "skipped")
    assert "unknown robot_id" in skipped_reasons          # arm-99
    assert "unparseable recorded_at" in skipped_reasons    # 'not a date'
    assert "invalid duration_seconds" in skipped_reasons   # 45.5 / -5 / 999999 / N/A
    assert "invalid quality" in skipped_reasons            # excellent / empty

    listing = client.get("/episodes", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()) > 0


def test_import_is_idempotent(client, login):
    headers = login("ops1@example.com")
    content = SEED_CSV.read_bytes()

    first = _upload(client, headers, content).json()
    second = _upload(client, headers, content).json()

    assert first["imported"] > 0
    assert second["imported"] == 0
    # every row that was valid the first time is present the second time;
    # rows that were in-file duplicates were already 'updated' on run one.
    assert second["updated"] == first["imported"] + first["updated"]
    assert second["skipped"] == first["skipped"]


def test_in_file_duplicate_rows_are_deduped(client, login):
    headers = login("ops1@example.com")
    row = b"episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"
    row += b"EP-50001,arm-01,pick cup,2026-08-01T10:00:00,60,Aline,good\n"
    row += b"EP-50001,arm-01,pick cup,2026-08-01T10:00:00,60,Aline,good\n"

    report = _upload(client, headers, row).json()
    assert report["rows_seen"] == 2
    assert report["imported"] == 1
    assert report["updated"] == 1


def test_clients_cannot_import(client, login):
    response = _upload(client, login("client-a@example.com"), b"episode_id\n")
    assert response.status_code == 403


def test_import_requires_auth(client):
    response = _upload(client, {}, b"episode_id\n")
    assert response.status_code == 401


def test_empty_and_malformed_rows_are_skipped_not_fatal(client, login):
    headers = login("ops1@example.com")
    content = (
        b"episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"
        b",arm-01,pick cup,2026-08-01T10:00:00,60,Aline,good\n"          # missing id
        b"EP-50002,arm-01,pick cup,2026-08-01T10:00:00,60\n"             # short row
        b"EP-50003,arm-01,pick cup,2026-08-01T10:00:00,60,Aline,good\n"  # valid
    )
    report = _upload(client, headers, content).json()
    assert report["skipped"] == 2
    assert report["imported"] == 1
