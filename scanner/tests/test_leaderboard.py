"""Tests for the funding movers leaderboard computation."""
from database import Database
from leaderboard import compute_movers


def test_compute_movers_orders_by_abs_quotient(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    # AUSDT: 0.001 -> 0.002  (+100%)
    db.insert_snapshot("AUSDT", 1000, 1.0, 0.001, None)
    db.insert_snapshot("AUSDT", 2000, 1.0, 0.002, None)
    # BUSDT: 0.001 -> 0.0005 (-50%)
    db.insert_snapshot("BUSDT", 1000, 1.0, 0.001, None)
    db.insert_snapshot("BUSDT", 2000, 1.0, 0.0005, None)
    # CUSDT: first funding is zero -> excluded (quotient undefined)
    db.insert_snapshot("CUSDT", 1000, 1.0, 0.0, None)
    db.insert_snapshot("CUSDT", 2000, 1.0, 0.01, None)

    movers = compute_movers(db.snapshots_since(0), top_n=5)
    assert [m.symbol for m in movers] == ["AUSDT", "BUSDT"]
    assert movers[0].quotient == 1.0
    assert movers[1].quotient == -0.5
    db.close()


def test_top_n_limit(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    for i in range(4):
        sym = f"S{i}USDT"
        db.insert_snapshot(sym, 1000, 1.0, 0.001, None)
        db.insert_snapshot(sym, 2000, 1.0, 0.001 * (i + 2), None)
    movers = compute_movers(db.snapshots_since(0), top_n=2)
    assert len(movers) == 2
    db.close()
