from __future__ import annotations

import json
import subprocess
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


def _strategy_path_from_program_entry(project_root: Path, program_entry: str) -> Path:
    module_name = str(program_entry).split(":", 1)[0].strip()
    return project_root / "src" / Path(*module_name.split(".")).with_suffix(".py")


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

    strategy_path = _strategy_path_from_program_entry(tmp_path, trader["program_entry"])
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


def test_server_create_trader_with_codex_fallback_bin_candidates(tmp_path: Path, monkeypatch) -> None:
    attempts: list[str] = []

    def fake_run(args, **kwargs):
        bin_path = str(args[0])
        attempts.append(bin_path)
        if bin_path == "codex":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")
        raise OSError("[WinError 2] system cannot find the file specified")

    monkeypatch.setattr("server.default_codex_bin", lambda _project_root: r"C:\also-missing\codex.cmd")
    monkeypatch.setattr("server.subprocess.run", fake_run)

    client = TestClient(create_app(project_root=tmp_path))
    client.post(
        "/api/seasons",
        json={
            "season": "S3",
            "market": "HK",
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "initial_capital": 1000000,
            "fee_rate": 0.0004,
            "symbol_pool": ["01810"],
        },
    )

    res = client.post(
        "/api/seasons/s3/traders/codex",
        json={
            "trader": "Fallback Bot",
            "style": "intraday",
            "symbols": ["01810"],
            "codex_bin": r"C:\missing\codex.cmd",
        },
    )
    assert res.status_code == 201
    payload = res.json()
    print("codex response (fallback test):", payload["codex"])
    assert payload["trader"]["slug"] == "fallback-bot"
    assert payload["codex"]["ok"] is True
    assert payload["codex"]["code"] == 0
    assert payload["codex"]["stdout"] == "ok"
    assert attempts[0] == r"C:\missing\codex.cmd"
    assert "codex" in attempts
    assert _trader_json(tmp_path, "s3", "fallback-bot").exists()


def test_server_create_trader_with_codex_auto_mode_creates_trader(tmp_path: Path, monkeypatch) -> None:
    def fake_run(args, **kwargs):
        _ = kwargs
        assert args[1] == "exec"
        trader_slug = "auto-fox"
        trader_dir = (
            tmp_path
            / "src"
            / "trader_incubator"
            / "core"
            / "skills"
            / "seasons"
            / "s4"
            / "traders"
            / trader_slug
        )
        trader_dir.mkdir(parents=True, exist_ok=True)
        (trader_dir / "trader.json").write_text(
            json.dumps(
                {
                    "trader": "Auto Fox",
                    "season": "S4",
                    "style": "mean-reversion/intraday",
                    "program_entry": "trader_incubator.core.skills.seasons.s4.traders.auto_fox.strategy:TraderProgram",
                    "initial_capital": 1000000.0,
                    "symbols": ["01810"],
                    "created_at": "2026-03-24T00:00:00Z",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (trader_dir / "strategy.py").write_text(
            "from exchange import TradingStrategy\n\nclass TraderProgram(TradingStrategy):\n    pass\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="created", stderr="")

    monkeypatch.setattr("server.subprocess.run", fake_run)
    monkeypatch.setattr("server.default_codex_bin", lambda _project_root: "codex")

    client = TestClient(create_app(project_root=tmp_path))
    client.post(
        "/api/seasons",
        json={
            "season": "S4",
            "market": "HK",
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "initial_capital": 1000000,
            "fee_rate": 0.0004,
            "symbol_pool": ["01810"],
        },
    )

    res = client.post(
        "/api/seasons/s4/traders/codex",
        json={
            "desired_count": 1,
        },
    )
    assert res.status_code == 201
    payload = res.json()
    print("codex response (auto create test):", payload["codex"])
    assert payload["codex"]["ok"] is True
    assert payload["codex"]["stdout"] == "created"
    assert len(payload["traders"]) == 1
    assert payload["traders"][0]["slug"] == "auto-fox"
    assert _trader_json(tmp_path, "s4", "auto-fox").exists()
