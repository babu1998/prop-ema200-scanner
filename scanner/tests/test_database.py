"""Tests for the SQLite persistence layer."""
from database import Database


def make_db(tmp_path) -> Database:
    return Database(str(tmp_path / "test.db"))


def test_last_snapshot_returns_most_recent(tmp_path):
    db = make_db(tmp_path)
    db.insert_snapshot("BTCUSDT", 1000, 50000.0, 0.0001, None)
    db.insert_snapshot("BTCUSDT", 2000, 51000.0, 0.0002, 1.0)
    db.insert_snapshot("ETHUSDT", 3000, 3000.0, -0.0001, None)

    row = db.last_snapshot("BTCUSDT")
    assert row is not None
    assert row["timestamp"] == 2000
    assert row["price"] == 51000.0
    assert db.last_snapshot("XRPUSDT") is None
    db.close()


def test_alert_cooldown_lookup(tmp_path):
    db = make_db(tmp_path)
    assert db.last_alert_ts("BTCUSDT") is None
    db.insert_alert("BTCUSDT", 1000, "PRICE_UP_FUNDING_DOWN")
    db.insert_alert("BTCUSDT", 5000, "PRICE_DOWN_FUNDING_UP")
    assert db.last_alert_ts("BTCUSDT") == 5000
    db.close()


def test_snapshots_since_and_prune(tmp_path):
    db = make_db(tmp_path)
    db.insert_snapshot("BTCUSDT", 1000, 1.0, 0.1, None)
    db.insert_snapshot("BTCUSDT", 2000, 2.0, 0.2, None)
    assert len(db.snapshots_since(1500)) == 1
    assert db.prune_snapshots(1500) == 1
    assert len(db.snapshots_since(0)) == 1
    db.close()
