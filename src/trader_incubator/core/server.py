from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from season import Season, SeasonTraderRef, slugify, to_module_name
from trader import Trader


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_project_root() -> Path:
    # .../src/trader_incubator/core/server.py -> project root
    return Path(__file__).resolve().parents[3]


def _seasons_root(project_root: Path) -> Path:
    return project_root / "src" / "trader_incubator" / "core" / "skills" / "seasons"


def _season_dir(project_root: Path, season_slug: str) -> Path:
    return _seasons_root(project_root) / season_slug


def _season_json_path(project_root: Path, season_slug: str) -> Path:
    return _season_dir(project_root, season_slug) / "season.json"


def _trader_dir(project_root: Path, season_slug: str, trader_slug: str) -> Path:
    return _season_dir(project_root, season_slug) / "traders" / trader_slug


def _trader_json_path(project_root: Path, season_slug: str, trader_slug: str) -> Path:
    return _trader_dir(project_root, season_slug, trader_slug) / "trader.json"


def _strategy_py_path(project_root: Path, season_slug: str, trader_slug: str) -> Path:
    return _trader_dir(project_root, season_slug, trader_slug) / "strategy.py"


def _read_json_file(path: Path) -> Any:
    if not path.exists():
        return []
    try:
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _season_to_response(season: Season) -> dict[str, Any]:
    payload = season.to_dict()
    payload["slug"] = season.slug
    return payload


def _trader_to_response(trader: Trader) -> dict[str, Any]:
    payload = trader.to_dict()
    payload["slug"] = trader.slug
    payload["season_slug"] = trader.season_slug
    return payload


def _load_season_or_404(project_root: Path, season_slug: str) -> Season:
    season_json = _season_json_path(project_root, season_slug)
    if not season_json.exists():
        raise HTTPException(status_code=404, detail=f"season not found: {season_slug}")
    return Season.load(season_slug=season_slug, project_root=project_root)


def _load_trader_or_404(project_root: Path, season_slug: str, trader_slug: str) -> Trader:
    trader_json = _trader_json_path(project_root, season_slug, trader_slug)
    if not trader_json.exists():
        raise HTTPException(status_code=404, detail=f"trader not found: {season_slug}/{trader_slug}")
    return Trader.load(season_slug=season_slug, trader_slug=trader_slug, project_root=project_root)


def _ensure_strategy_template(strategy_path: Path, class_name: str = "TraderProgram") -> None:
    if strategy_path.exists():
        return
    strategy_path.parent.mkdir(parents=True, exist_ok=True)
    strategy_path.write_text(
        (
            "from __future__ import annotations\n\n"
            "from datetime import datetime\n"
            "from typing import Mapping\n\n"
            "import pandas as pd\n\n"
            "from exchange import TradingStrategy\n\n\n"
            f"class {class_name}(TradingStrategy):\n"
            "    def on_pre_open(self, event_time: datetime) -> None:\n"
            "        pass\n\n"
            "    def on_minute(self, event_time: datetime, latest_bars: Mapping[str, pd.Series]) -> None:\n"
            "        pass\n\n"
            "    def on_post_close(self, event_time: datetime) -> None:\n"
            "        pass\n"
        ),
        encoding="utf-8",
    )


def _write_season(project_root: Path, season: Season) -> Path:
    path = _season_json_path(project_root, season.slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(season.to_json(), encoding="utf-8")
    return path


def _write_trader(project_root: Path, season_slug: str, trader: Trader) -> Path:
    path = _trader_json_path(project_root, season_slug, trader.slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(trader.to_json(), encoding="utf-8")
    return path


class SeasonCreateRequest(BaseModel):
    season: str
    market: str
    start_date: str
    end_date: str | None = None
    initial_capital: float = 1_000_000.0
    fee_rate: float = 0.0004
    symbol_pool: list[str] = Field(default_factory=list)


class SeasonUpdateRequest(BaseModel):
    season: str | None = None
    market: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    initial_capital: float | None = None
    fee_rate: float | None = None
    symbol_pool: list[str] | None = None


class TraderCreateRequest(BaseModel):
    trader: str
    style: str
    program_entry: str | None = None
    initial_capital: float | None = None
    symbols: list[str] = Field(default_factory=list)


class TraderUpdateRequest(BaseModel):
    trader: str | None = None
    style: str | None = None
    program_entry: str | None = None
    initial_capital: float | None = None
    symbols: list[str] | None = None


def create_app(project_root: Path | str | None = None) -> FastAPI:
    resolved_root = Path(project_root) if project_root is not None else _default_project_root()
    resolved_root = resolved_root.resolve()

    app = FastAPI(title="Trader Incubator API", version="0.1.0")
    app.state.project_root = resolved_root

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/seasons")
    def list_seasons() -> list[dict[str, Any]]:
        root = _seasons_root(app.state.project_root)
        if not root.exists():
            return []
        items: list[dict[str, Any]] = []
        for season_json in sorted(root.glob("*/season.json")):
            try:
                season = Season.from_json(season_json.read_text(encoding="utf-8"))
            except Exception:
                continue
            items.append(_season_to_response(season))
        return items

    @app.post("/api/seasons", status_code=201)
    def create_season(payload: SeasonCreateRequest) -> dict[str, Any]:
        season = Season(
            season=payload.season,
            market=payload.market,
            start_date=payload.start_date,
            end_date=payload.end_date,
            initial_capital=payload.initial_capital,
            fee_rate=payload.fee_rate,
            symbol_pool=payload.symbol_pool,
            traders=[],
            created_at=_utc_now(),
        )
        season_slug = season.slug
        season_json = _season_json_path(app.state.project_root, season_slug)
        if season_json.exists():
            raise HTTPException(status_code=409, detail=f"season already exists: {season_slug}")
        _write_season(project_root=app.state.project_root, season=season)
        return _season_to_response(season)

    @app.get("/api/seasons/{season_slug}")
    def get_season(season_slug: str) -> dict[str, Any]:
        season = _load_season_or_404(app.state.project_root, season_slug)
        return _season_to_response(season)

    @app.put("/api/seasons/{season_slug}")
    def update_season(season_slug: str, payload: SeasonUpdateRequest) -> dict[str, Any]:
        project_root = app.state.project_root
        current = _load_season_or_404(project_root, season_slug)
        updated = Season(
            season=payload.season if payload.season is not None else current.season,
            market=payload.market if payload.market is not None else current.market,
            start_date=payload.start_date if payload.start_date is not None else current.start_date,
            end_date=payload.end_date if payload.end_date is not None else current.end_date,
            initial_capital=(
                float(payload.initial_capital)
                if payload.initial_capital is not None
                else float(current.initial_capital)
            ),
            fee_rate=float(payload.fee_rate) if payload.fee_rate is not None else float(current.fee_rate),
            symbol_pool=payload.symbol_pool if payload.symbol_pool is not None else list(current.symbol_pool),
            traders=list(current.traders),
            created_at=current.created_at or _utc_now(),
        )
        new_slug = updated.slug
        old_dir = _season_dir(project_root, season_slug)
        new_dir = _season_dir(project_root, new_slug)
        if new_slug != season_slug and new_dir.exists():
            raise HTTPException(status_code=409, detail=f"season already exists: {new_slug}")
        if new_slug != season_slug and old_dir.exists():
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_dir), str(new_dir))
        _write_season(project_root=project_root, season=updated)
        return _season_to_response(updated)

    @app.delete("/api/seasons/{season_slug}")
    def delete_season(season_slug: str) -> dict[str, bool]:
        season_dir = _season_dir(app.state.project_root, season_slug)
        if not season_dir.exists():
            raise HTTPException(status_code=404, detail=f"season not found: {season_slug}")
        shutil.rmtree(season_dir)
        return {"ok": True}

    @app.get("/api/seasons/{season_slug}/traders")
    def list_traders(season_slug: str) -> list[dict[str, Any]]:
        _load_season_or_404(app.state.project_root, season_slug)
        traders = Trader.load_all(season_slug=season_slug, project_root=app.state.project_root)
        return [_trader_to_response(item) for item in traders]

    @app.get("/api/seasons/{season_slug}/equity")
    def get_season_equity(season_slug: str) -> dict[str, list[dict[str, Any]]]:
        _load_season_or_404(app.state.project_root, season_slug)
        traders_dir = _season_dir(app.state.project_root, season_slug) / "traders"
        if not traders_dir.exists():
            return {}
        result: dict[str, list[dict[str, Any]]] = {}
        for trader_folder in sorted(traders_dir.glob("*")):
            if not trader_folder.is_dir():
                continue
            payload = _read_json_file(trader_folder / "equity.json")
            if isinstance(payload, list):
                result[trader_folder.name] = payload
        return result

    @app.get("/api/seasons/{season_slug}/orders")
    def get_season_orders(season_slug: str) -> dict[str, list[dict[str, Any]]]:
        _load_season_or_404(app.state.project_root, season_slug)
        traders_dir = _season_dir(app.state.project_root, season_slug) / "traders"
        if not traders_dir.exists():
            return {}
        result: dict[str, list[dict[str, Any]]] = {}
        for trader_folder in sorted(traders_dir.glob("*")):
            if not trader_folder.is_dir():
                continue
            payload = _read_json_file(trader_folder / "orders.json")
            if isinstance(payload, list):
                result[trader_folder.name] = payload
        return result

    @app.post("/api/seasons/{season_slug}/traders", status_code=201)
    def create_trader(season_slug: str, payload: TraderCreateRequest) -> dict[str, Any]:
        project_root = app.state.project_root
        season = _load_season_or_404(project_root, season_slug)

        trader = Trader(
            trader=payload.trader,
            season=season.season,
            style=payload.style,
            program_entry=payload.program_entry or "",
            initial_capital=payload.initial_capital,
            symbols=list(payload.symbols),
            created_at=_utc_now(),
        )
        if not trader.program_entry:
            season_module = to_module_name(season.season)
            trader_module = trader.module_name
            trader.program_entry = f"skills.seasons.{season_module}.traders.{trader_module}.strategy:TraderProgram"

        trader_json = _trader_json_path(project_root, season_slug, trader.slug)
        if trader_json.exists():
            raise HTTPException(status_code=409, detail=f"trader already exists: {season_slug}/{trader.slug}")

        _write_trader(project_root=project_root, season_slug=season_slug, trader=trader)
        _ensure_strategy_template(_strategy_py_path(project_root, season_slug, trader.slug))

        season.add_trader(
            SeasonTraderRef(
                trader=trader.trader,
                style=trader.style,
                program_entry=trader.program_entry,
            )
        )
        _write_season(project_root=project_root, season=season)
        return _trader_to_response(trader)

    @app.get("/api/seasons/{season_slug}/traders/{trader_slug}")
    def get_trader(season_slug: str, trader_slug: str) -> dict[str, Any]:
        _load_season_or_404(app.state.project_root, season_slug)
        trader = _load_trader_or_404(app.state.project_root, season_slug, trader_slug)
        return _trader_to_response(trader)

    @app.put("/api/seasons/{season_slug}/traders/{trader_slug}")
    def update_trader(season_slug: str, trader_slug: str, payload: TraderUpdateRequest) -> dict[str, Any]:
        project_root = app.state.project_root
        season = _load_season_or_404(project_root, season_slug)
        current = _load_trader_or_404(project_root, season_slug, trader_slug)

        updated = Trader(
            trader=payload.trader if payload.trader is not None else current.trader,
            season=season.season,
            style=payload.style if payload.style is not None else current.style,
            program_entry=payload.program_entry if payload.program_entry is not None else current.program_entry,
            initial_capital=(
                float(payload.initial_capital)
                if payload.initial_capital is not None
                else (float(current.initial_capital) if current.initial_capital is not None else None)
            ),
            symbols=payload.symbols if payload.symbols is not None else list(current.symbols),
            created_at=current.created_at or _utc_now(),
        )

        new_slug = updated.slug
        old_dir = _trader_dir(project_root, season_slug, trader_slug)
        new_dir = _trader_dir(project_root, season_slug, new_slug)
        if new_slug != trader_slug and new_dir.exists():
            raise HTTPException(status_code=409, detail=f"trader already exists: {season_slug}/{new_slug}")
        if new_slug != trader_slug and old_dir.exists():
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_dir), str(new_dir))

        _write_trader(project_root=project_root, season_slug=season_slug, trader=updated)
        _ensure_strategy_template(_strategy_py_path(project_root, season_slug, new_slug))

        season.add_trader(
            SeasonTraderRef(
                trader=updated.trader,
                style=updated.style,
                program_entry=updated.program_entry,
            )
        )
        season.traders = [ref for ref in season.traders if ref.slug != trader_slug or ref.slug == updated.slug]
        _write_season(project_root=project_root, season=season)
        return _trader_to_response(updated)

    @app.delete("/api/seasons/{season_slug}/traders/{trader_slug}")
    def delete_trader(season_slug: str, trader_slug: str) -> dict[str, bool]:
        project_root = app.state.project_root
        season = _load_season_or_404(project_root, season_slug)
        target_dir = _trader_dir(project_root, season_slug, trader_slug)
        if not target_dir.exists():
            raise HTTPException(status_code=404, detail=f"trader not found: {season_slug}/{trader_slug}")
        shutil.rmtree(target_dir)
        season.traders = [ref for ref in season.traders if slugify(ref.trader) != trader_slug]
        _write_season(project_root=project_root, season=season)
        return {"ok": True}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
