"""Pytest configuration and shared fixtures."""
from __future__ import annotations

import pytest

import app.database as _db_module


@pytest.fixture(autouse=True)
async def reset_db_connection():
    """Close and clear the global DB connection before each test so each test
    gets a fresh connection pointing at its own tmp_path-based cache."""
    await _db_module.close_db()
    yield
    await _db_module.close_db()
