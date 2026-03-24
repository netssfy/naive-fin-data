from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from live import run_all_seasons_live
from season import Season, SeasonTraderRef, slugify, to_module_name
from trader import Trader
from trader_research import default_codex_bin

_live_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="live-runner")


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


def _strategy_path_from_program_entry(project_root: Path, program_entry: str, fallback: Path) -> Path:
    module_name = str(program_entry).split(":", 1)[0].strip()
    if not module_name:
        return fallback
    return project_root / "src" / Path(*module_name.split(".")).with_suffix(".py")


def _candidate_codex_bins(project_root: Path, requested: str | None) -> list[str]:
    local_name = "codex.cmd" if os.name == "nt" else "codex"
    candidates: list[str] = []
    raw = (requested or "").strip()
    if raw:
        candidates.append(raw)
    auto = default_codex_bin(project_root)
    if auto:
        candidates.append(auto)
    candidates.extend(
        [
            str(project_root / "apps" / "web" / "node_modules" / ".bin" / local_name),
            str(project_root / "src" / "trader_incubator" / "apps" / "web" / "node_modules" / ".bin" / local_name),
            "codex",
        ]
    )
    uniq: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(key)
    return uniq


def _read_json_file(path: Path) -> Any:
    if not path.exists():
        return []
    try:
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


class TraderCreateWithCodexRequest(BaseModel):
    trader: str | None = None
    style: str | None = None
    program_entry: str | None = None
    symbols: list[str] = Field(default_factory=list)
    codex_bin: str | None = None
    desired_count: int = 1
    stream: bool = False


def create_app(project_root: Path | str | None = None) -> FastAPI:
    resolved_root = Path(project_root) if project_root is not None else _default_project_root()
    resolved_root = resolved_root.resolve()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()

        def _run_live() -> None:
            try:
                logger.info("[live] starting run_all_seasons_live, project_root=%s", resolved_root)
                run_all_seasons_live(project_root=resolved_root)
                logger.info("[live] run_all_seasons_live exited normally")
            except Exception:
                logger.exception("[live] run_all_seasons_live crashed")

        future = loop.run_in_executor(_live_executor, _run_live)
        try:
            yield
        finally:
            _live_executor.shutdown(wait=False, cancel_futures=True)
            future.cancel()

    app = FastAPI(title="Trader Incubator API", version="0.1.0", lifespan=lifespan)
    app.state.project_root = resolved_root

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            raise exc
        logger.error(
            "Unhandled exception on %s %s\n%s",
            request.method,
            request.url,
            traceback.format_exc(),
        )
        return JSONResponse(status_code=500, content={"detail": str(exc)})

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
            trader.program_entry = (
                f"trader_incubator.core.skills.seasons.{season_module}.traders.{trader_module}.strategy:TraderProgram"
            )

        trader_json = _trader_json_path(project_root, season_slug, trader.slug)
        if trader_json.exists():
            raise HTTPException(status_code=409, detail=f"trader already exists: {season_slug}/{trader.slug}")

        _write_trader(project_root=project_root, season_slug=season_slug, trader=trader)
        strategy_path = _strategy_path_from_program_entry(
            project_root=project_root,
            program_entry=trader.program_entry,
            fallback=_strategy_py_path(project_root, season_slug, trader.slug),
        )
        _ensure_strategy_template(strategy_path)

        season.add_trader(
            SeasonTraderRef(
                trader=trader.trader,
                style=trader.style,
                program_entry=trader.program_entry,
            )
        )
        _write_season(project_root=project_root, season=season)
        return _trader_to_response(trader)

    @app.post("/api/seasons/{season_slug}/traders/codex", status_code=201)
    def create_trader_with_codex(season_slug: str, payload: TraderCreateWithCodexRequest):
        project_root = app.state.project_root
        season = _load_season_or_404(project_root, season_slug)
        codex_bin_candidates = _candidate_codex_bins(project_root, payload.codex_bin)

        # Manual mode: caller provides trader/style and server scaffolds first.
        if payload.trader and payload.style:
            trader_slug = slugify(payload.trader)
            if _trader_json_path(project_root, season_slug, trader_slug).exists():
                raise HTTPException(status_code=409, detail=f"trader already exists: {season_slug}/{trader_slug}")

            trader = Trader(
                trader=payload.trader,
                season=season.season,
                style=payload.style,
                program_entry=payload.program_entry or "",
                initial_capital=season.initial_capital,
                symbols=list(payload.symbols),
                created_at=_utc_now(),
            )
            if not trader.program_entry:
                season_module = to_module_name(season.season)
                trader_module = trader.module_name
                trader.program_entry = (
                    f"trader_incubator.core.skills.seasons.{season_module}.traders.{trader_module}.strategy:TraderProgram"
                )
            _write_trader(project_root=project_root, season_slug=season_slug, trader=trader)
            strategy_path = _strategy_path_from_program_entry(
                project_root=project_root,
                program_entry=trader.program_entry,
                fallback=_strategy_py_path(project_root, season_slug, trader.slug),
            )
            _ensure_strategy_template(strategy_path)
            season.add_trader(
                SeasonTraderRef(
                    trader=trader.trader,
                    style=trader.style,
                    program_entry=trader.program_entry,
                )
            )
            _write_season(project_root=project_root, season=season)

            codex_prompt = (
                "Use $shuaishuai to follow trader creation conventions.\n"
                f"Improve this strategy file only: {strategy_path}\n"
                f"Season: {season.season} ({season.market}), Trader: {trader.trader}, Style: {trader.style}\n"
                f"Allowed symbols: {trader.symbols if trader.symbols else season.symbol_pool}\n"
                "Implement practical on_minute logic and keep code executable.\n"
                "Do not modify other files."
            )
        else:
            if payload.trader or payload.style:
                raise HTTPException(status_code=422, detail="trader and style must be provided together")
            before = {item.slug for item in Trader.load_all(season_slug=season_slug, project_root=project_root)}
            script_path = (
                project_root
                / "src"
                / "trader_incubator"
                / "core"
                / "skills"
                / "帅帅"
                / "scripts"
                / "create_trader_skills.py"
            )
            season_json = _season_json_path(project_root=project_root, season_slug=season_slug)
            desired_count = max(int(payload.desired_count or 1), 1)
            codex_prompt = (
                "Use $shuaishuai and follow references/create_trader.md.\n"
                f"Create exactly {desired_count} new trader(s) for season '{season.season}' (slug '{season_slug}').\n"
                f"Season config path: {season_json}\n"
                f"Use script: {script_path}\n"
                f"Market: {season.market}. Season symbol_pool: {season.symbol_pool}\n"
                "Each trader must have distinct style. Run the script(s) to create trader skill folders and update season roster.\n"
                "Only change files under src/trader_incubator/core/skills/seasons/<season-slug>/traders and the season.json roster."
            )

        def _build_response_payload(codex_result: dict[str, Any], fail_on_empty: bool) -> dict[str, Any]:
            if payload.trader and payload.style:
                return {"trader": _trader_to_response(trader), "codex": codex_result}
            after = {item.slug for item in Trader.load_all(season_slug=season_slug, project_root=project_root)}
            created_slugs = sorted(after - before)
            if not created_slugs:
                detail = codex_result["stderr"] or codex_result["stdout"] or "codex did not create any trader"
                logger.error(
                    "codex did not create any trader for season '%s'\nreturncode: %s\nstdout: %s\nstderr: %s",
                    season_slug,
                    codex_result.get("code"),
                    codex_result.get("stdout"),
                    codex_result.get("stderr"),
                )
                if fail_on_empty:
                    raise HTTPException(status_code=500, detail=detail)
                return {"traders": [], "codex": codex_result, "error": detail}
            created = [
                _trader_to_response(_load_trader_or_404(project_root, season_slug, slug))
                for slug in created_slugs
            ]
            return {"traders": created, "codex": codex_result}

        if payload.stream:
            def _iter_events():
                yield json.dumps({"type": "status", "message": "codex task queued"}, ensure_ascii=False) + "\n"
                last_os_error = ""
                codex_result = {"ok": False, "code": -1, "stdout": "", "stderr": ""}
                for codex_bin in codex_bin_candidates:
                    yield json.dumps(
                        {"type": "status", "message": f"trying codex bin: {codex_bin}", "bin": codex_bin},
                        ensure_ascii=False,
                    ) + "\n"
                    try:
                        proc = subprocess.Popen(
                            [codex_bin, "exec", "--sandbox", "workspace-write", "--full-auto", codex_prompt],
                            cwd=str(project_root),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            bufsize=1,
                        )
                        output_lines: list[str] = []
                        if proc.stdout is not None:
                            for raw_line in proc.stdout:
                                line = raw_line.rstrip()
                                if not line:
                                    continue
                                output_lines.append(line)
                                yield json.dumps({"type": "log", "message": line}, ensure_ascii=False) + "\n"
                        rc = int(proc.wait())
                        codex_result = {
                            "ok": rc == 0,
                            "code": rc,
                            "stdout": "\n".join(output_lines).strip(),
                            "stderr": "",
                        }
                        break
                    except OSError as exc:
                        last_os_error = str(exc)
                        yield json.dumps({"type": "status", "message": f"bin failed: {exc}"}, ensure_ascii=False) + "\n"
                        continue
                if codex_result["code"] == -1 and not codex_result["stderr"]:
                    codex_result["stderr"] = (
                        f"{last_os_error or '[WinError 2] system cannot find codex executable'}; "
                        f"tried={codex_bin_candidates}"
                    )
                final_payload = _build_response_payload(codex_result, fail_on_empty=False)
                yield json.dumps({"type": "final", "payload": final_payload}, ensure_ascii=False) + "\n"

            return StreamingResponse(_iter_events(), media_type="application/x-ndjson")

        last_os_error: str = ""
        codex_result = {"ok": False, "code": -1, "stdout": "", "stderr": ""}
        for codex_bin in codex_bin_candidates:
            try:
                codex = subprocess.run(
                    [codex_bin, "exec", "--sandbox", "workspace-write", "--full-auto", codex_prompt],
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=180,
                )
                codex_result = {
                    "ok": codex.returncode == 0,
                    "code": codex.returncode,
                    "stdout": (codex.stdout or "").strip(),
                    "stderr": (codex.stderr or "").strip(),
                }
                break
            except subprocess.TimeoutExpired as exc:
                codex_result = {
                    "ok": False,
                    "code": -2,
                    "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
                    "stderr": f"codex exec timed out after 180 seconds (bin={codex_bin})",
                }
                break
            except OSError as exc:
                last_os_error = str(exc)
                continue
        if codex_result["code"] == -1 and not codex_result["stderr"]:
            codex_result["stderr"] = (
                f"{last_os_error or '[WinError 2] system cannot find codex executable'}; "
                f"tried={codex_bin_candidates}"
            )
        return _build_response_payload(codex_result, fail_on_empty=True)

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
        strategy_path = _strategy_path_from_program_entry(
            project_root=project_root,
            program_entry=updated.program_entry,
            fallback=_strategy_py_path(project_root, season_slug, new_slug),
        )
        _ensure_strategy_template(strategy_path)

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
