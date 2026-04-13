"""Tests for scanner cancel flag and per-device count tracking."""
from __future__ import annotations

import pytest

from app.scanner import ScanProgress


class TestScanProgressCancelFlag:
    def test_request_cancel_sets_flag_while_running(self) -> None:
        p = ScanProgress()
        p.running = True
        p.request_cancel()
        assert p.cancelled is True

    def test_request_cancel_ignored_when_not_running(self) -> None:
        p = ScanProgress()
        p.running = False
        p.request_cancel()
        assert p.cancelled is False

    def test_cancelled_included_in_to_dict(self) -> None:
        p = ScanProgress()
        assert "cancelled" in p.to_dict()
        assert p.to_dict()["cancelled"] is False

    def test_cancelled_true_reflected_in_to_dict(self) -> None:
        p = ScanProgress()
        p.running = True
        p.request_cancel()
        assert p.to_dict()["cancelled"] is True


class TestScanProgressDeviceCounts:
    def test_device_counts_empty_by_default(self) -> None:
        p = ScanProgress()
        assert p.device_counts == []

    def test_device_counts_in_to_dict(self) -> None:
        p = ScanProgress()
        p.device_counts.append({"label": "Alice's Phone", "found": 47})
        p.device_counts.append({"label": "Bob's Phone", "found": 12})
        d = p.to_dict()
        assert d["device_counts"] == [
            {"label": "Alice's Phone", "found": 47},
            {"label": "Bob's Phone", "found": 12},
        ]


class TestScanProgressPercent:
    def test_percent_zero_when_total_unknown(self) -> None:
        p = ScanProgress()
        assert p.percent == 0

    def test_percent_computed_correctly(self) -> None:
        p = ScanProgress()
        p.total = 100
        p.scanned = 50
        assert p.percent == 50

    def test_percent_capped_at_100(self) -> None:
        p = ScanProgress()
        p.total = 10
        p.scanned = 15
        assert p.percent == 100
