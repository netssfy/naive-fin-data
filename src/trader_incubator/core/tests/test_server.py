from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from server import create_app


def _season_json(project_root: Path, season_slug: str) -> Path:
    return (
        project_root
        / "src"
        / "trader_incubator"
        / "core"
        / "skills"
        / "seasons"
        / season_slug
        / "season.json"
    )


def _trader_json(project_root: Path, season_slug: str, trader_slug: str) -> Path:
    return (
        project_root
        / "src"
        / "trader_incubator"
        / "core"
        / "skills"
        / "seasons"
        / season_slug
        / "traders"
        / trader_slug
        / "trader.json"
    )


def test_server_season_crud(tmp_path: Path) -> None:
    client = TestClient(create_app(project_root=tmp_path))

    res = client.post(
        "/api/seasons",
        json={
            "season": "Season API 1",
            "market": "HK",
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "initial_capital": 1000000,
            "fee_rate": 0.0004,
            "symbol_pool": ["00700", "01810"],
        },
    )
    assert res.status_code == 201
    season = res.json()
    assert season["slug"] == "season-api-1"
    assert _season_json(tmp_path, "season-api-1").exists()

    res = client.get("/api/seasons")
    assert res.status_code == 200
    assert len(res.json()) == 1

    res = client.put("/api/seasons/season-api-1", json={"season": "Season API X", "fee_rate": 0.001})
    assert res.status_code == 200
    season = res.json()
    assert season["slug"] == "season-api-x"
    assert _season_json(tmp_path, "season-api-x").exists()

    res = client.delete("/api/seasons/season-api-x")
    assert res.status_code == 200
    assert not _season_json(tmp_path, "season-api-x").exists()


def test_server_trader_crud(tmp_path: Path) -> None:
    client = TestClient(create_app(project_root=tmp_path))
    client.post(
        "/api/seasons",
        json={
            "season": "S1",
            "market": "HK",
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "initial_capital": 1000000,
            "fee_rate": 0.0004,
            "symbol_pool": ["00700"],
        },
    )

    res = client.post(
        "/api/seasons/s1/traders",
        json={
            "trader": "Alice Wolf",
            "style": "swing",
            "symbols": ["00700"],
        },
    )
    assert res.status_code == 201
    trader = res.json()
    assert trader["slug"] == "alice-wolf"
    assert _trader_json(tmp_path, "s1", "alice-wolf").exists()

    strategy_path = _trader_json(tmp_path, "s1", "alice-wolf").parent / "strategy.py"
    assert strategy_path.exists()

    res = client.put("/api/seasons/s1/traders/alice-wolf", json={"trader": "Alice Pro", "style": "intraday"})
    assert res.status_code == 200
    trader = res.json()
    assert trader["slug"] == "alice-pro"
    assert _trader_json(tmp_path, "s1", "alice-pro").exists()

    season_json = json.loads(_season_json(tmp_path, "s1").read_text(encoding="utf-8"))
    assert any(item["trader"] == "Alice Pro" for item in season_json["traders"])

    res = client.get("/api/seasons/s1/equity")
    assert res.status_code == 200
    assert "alice-pro" in res.json()

    res = client.get("/api/seasons/s1/orders")
    assert res.status_code == 200
    assert "alice-pro" in res.json()

    res = client.delete("/api/seasons/s1/traders/alice-pro")
    assert res.status_code == 200
    assert not _trader_json(tmp_path, "s1", "alice-pro").exists()


def test_server_create_trader_with_codex(tmp_path: Path) -> None:
    client = TestClient(create_app(project_root=tmp_path))
    client.post(
        "/api/seasons",
        json={
            "season": "S2",
            "market": "US",
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "initial_capital": 2000000,
            "fee_rate": 0.0005,
            "symbol_pool": ["AAPL", "MSFT"],
        },
    )

    res = client.post(
        "/api/seasons/s2/traders/codex",
        json={
            "trader": "Nova Hawk",
            "style": "trend-following/swing/risk-budget",
            "symbols": ["AAPL"],
        },
    )
    assert res.status_code == 201
    payload = res.json()
    assert payload["trader"]["slug"] == "nova-hawk"
    assert isinstance(payload["codex"]["ok"], bool)
    assert _trader_json(tmp_path, "s2", "nova-hawk").exists()
