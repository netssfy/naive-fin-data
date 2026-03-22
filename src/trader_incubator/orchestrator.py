from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from trader_incubator.live import list_valid_season_slugs
from trader_incubator.season import Season
from trader_incubator.trader import Trader


DEFAULT_STATE_PATH = ".tmp/trader_incubator/orchestrator_state.json"
DEFAULT_LOOP_TIMEZONE = "Asia/Shanghai"

MARKET_TIMEZONE = {
    "a_share": "Asia/Shanghai",
    "ashare": "Asia/Shanghai",
    "cn": "Asia/Shanghai",
    "china": "Asia/Shanghai",
    "hk": "Asia/Hong_Kong",
    "hkex": "Asia/Hong_Kong",
    "us": "America/New_York",
    "usa": "America/New_York",
}

MARKET_SESSIONS = {
    "cn": [(dtime(9, 30), dtime(11, 30)), (dtime(13, 0), dtime(15, 0))],
    "hk": [(dtime(9, 30), dtime(12, 0)), (dtime(13, 0), dtime(16, 0))],
    "us": [(dtime(9, 30), dtime(16, 0))],
}


def _normalize_market(raw_market: str) -> str:
    text = str(raw_market).strip().lower()
    if text in {"a_share", "ashare", "cn", "china"}:
        return "cn"
    if text in {"hk", "hkex"}:
        return "hk"
    if text in {"us", "usa"}:
        return "us"
    return text


def _is_weekday(local_now: datetime) -> bool:
    return local_now.weekday() < 5


def _in_session(local_now: datetime, sessions: list[tuple[dtime, dtime]]) -> bool:
    current = local_now.time()
    for start_at, end_at in sessions:
        if start_at <= current < end_at:
            return True
    return False


def _is_market_open(market: str, now_utc: datetime) -> bool:
    normalized = _normalize_market(market)
    if normalized not in MARKET_SESSIONS:
        return False
    tz_name = MARKET_TIMEZONE.get(normalized, DEFAULT_LOOP_TIMEZONE)
    local_now = now_utc.astimezone(ZoneInfo(tz_name))
    if not _is_weekday(local_now):
        return False
    return _in_session(local_now, MARKET_SESSIONS[normalized])


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass(frozen=True)
class TraderTask:
    season_slug: str
    trader_slug: str
    trader_name: str
    strategy_path: Path
    program_entry: str
    style: str


def _program_entry_to_path(project_root: Path, program_entry: str) -> Path:
    module_name = str(program_entry).split(":", 1)[0].strip()
    if not module_name:
        return project_root
    return project_root / "src" / Path(*module_name.split(".")).with_suffix(".py")


def _discover_trader_tasks(project_root: Path, season_slugs: list[str]) -> list[TraderTask]:
    tasks: list[TraderTask] = []
    for season_slug in season_slugs:
        for trader in Trader.load_all(season_slug=season_slug, project_root=project_root):
            strategy_path = _program_entry_to_path(project_root=project_root, program_entry=trader.program_entry)
            tasks.append(
                TraderTask(
                    season_slug=season_slug,
                    trader_slug=trader.slug,
                    trader_name=trader.trader,
                    strategy_path=strategy_path,
                    program_entry=trader.program_entry,
                    style=trader.style,
                )
            )
    return tasks


def _build_research_prompt(task: TraderTask) -> str:
    return (
        f"你是量化策略工程师。请对交易员 {task.trader_name}（season={task.season_slug}）做非交易时段复盘与改进。\n"
        f"策略风格：{task.style}\n"
        f"策略入口：{task.program_entry}\n"
        f"策略文件：{task.strategy_path}\n"
        "任务要求：\n"
        "1) 审查当前策略逻辑与风险点，给出简短复盘结论。\n"
        "2) 直接在策略文件中实现可执行的改进（避免空函数）。\n"
        "3) 不要改动无关文件；仅做与策略改进相关的最小变更。\n"
        "4) 完成后输出改动摘要和下一步验证建议。\n"
    )


def _run_command(command: list[str], cwd: Path, dry_run: bool) -> int:
    if dry_run:
        print(f"[DRY-RUN] cwd={cwd} cmd={command}")
        return 0
    proc = subprocess.run(command, cwd=str(cwd), check=False)
    return int(proc.returncode)


def _default_codex_bin(project_root: Path) -> str:
    local_bin = project_root / "apps" / "web" / "node_modules" / ".bin"
    local_name = "codex.cmd" if os.name == "nt" else "codex"
    local_path = local_bin / local_name
    if local_path.exists():
        return str(local_path)
    resolved = shutil.which("codex")
    if resolved:
        return resolved
    return "codex"


class Orchestrator:
    def __init__(
        self,
        project_root: Path,
        loop_timezone: str,
        poll_seconds: int,
        state_file: Path,
        dry_run: bool,
        codex_bin: str,
    ) -> None:
        self.project_root = project_root
        self.loop_tz = ZoneInfo(loop_timezone)
        self.poll_seconds = max(int(poll_seconds), 5)
        self.state_file = state_file
        self.dry_run = bool(dry_run)
        self.codex_bin = str(codex_bin).strip() or "codex"
        self.live_process: subprocess.Popen | None = None

    def run(self, once: bool = False) -> int:
        while True:
            now = datetime.now(ZoneInfo("UTC"))
            cycle_day = now.astimezone(self.loop_tz).date().isoformat()
            valid_seasons = list_valid_season_slugs(project_root=self.project_root, timezone=str(self.loop_tz))
            season_markets = self._load_season_markets(valid_seasons)
            trading_now = any(_is_market_open(market=item, now_utc=now) for item in season_markets.values())

            if trading_now:
                self._ensure_live_running()
            else:
                self._ensure_live_stopped()
                self._run_research_once_per_day(cycle_day=cycle_day, season_slugs=valid_seasons)

            if once:
                self._ensure_live_stopped()
                return 0
            time.sleep(self.poll_seconds)

    def _load_season_markets(self, season_slugs: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for season_slug in season_slugs:
            try:
                season = Season.load(season_slug=season_slug, project_root=self.project_root)
            except Exception:
                continue
            out[season_slug] = _normalize_market(season.market)
        return out

    def _ensure_live_running(self) -> None:
        if self.live_process is not None and self.live_process.poll() is None:
            return
        command = [
            "python",
            "-m",
            "trader_incubator.live",
            "--all-seasons",
            "--project-root",
            str(self.project_root),
        ]
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "")
        src_path = str(self.project_root / "src")
        env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
        if self.dry_run:
            print(f"[DRY-RUN] start live: {command}")
            return
        self.live_process = subprocess.Popen(command, cwd=str(self.project_root), env=env)
        print(f"[ORCH] live started pid={self.live_process.pid}")

    def _ensure_live_stopped(self) -> None:
        if self.live_process is None:
            return
        if self.live_process.poll() is not None:
            self.live_process = None
            return
        self.live_process.terminate()
        try:
            self.live_process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.live_process.kill()
            self.live_process.wait(timeout=5)
        print("[ORCH] live stopped")
        self.live_process = None

    def _run_research_once_per_day(self, cycle_day: str, season_slugs: list[str]) -> None:
        state = _load_json(self.state_file)
        if state.get("last_research_day") == cycle_day:
            return

        tasks = _discover_trader_tasks(project_root=self.project_root, season_slugs=season_slugs)
        for task in tasks:
            self._run_single_trader_research(task)
        state["last_research_day"] = cycle_day
        _save_json(self.state_file, state)
        print(f"[ORCH] research done day={cycle_day} traders={len(tasks)}")

    def _run_single_trader_research(self, task: TraderTask) -> None:
        prompt = _build_research_prompt(task)
        command = [self.codex_bin, "exec", prompt]
        print(f"[ORCH] research season={task.season_slug} trader={task.trader_slug}")
        rc = _run_command(command=command, cwd=self.project_root, dry_run=self.dry_run)
        if rc != 0:
            print(
                f"[ORCH][WARN] codex task failed season={task.season_slug} "
                f"trader={task.trader_slug} code={rc}"
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trader incubator orchestrator loop")
    parser.add_argument("--project-root", default=".", help="project root path")
    parser.add_argument("--timezone", default=DEFAULT_LOOP_TIMEZONE, help="orchestrator timezone")
    parser.add_argument("--poll-seconds", type=int, default=30, help="main loop polling interval")
    parser.add_argument("--once", action="store_true", help="run only one cycle")
    parser.add_argument("--dry-run", action="store_true", help="print actions without executing child processes")
    parser.add_argument(
        "--codex-bin",
        default="",
        help="codex cli executable (default: auto-detect project-local bin, then PATH)",
    )
    parser.add_argument("--state-file", default=DEFAULT_STATE_PATH, help="path to state json file")
    parser.add_argument(
        "--print-live-command",
        action="store_true",
        help="print the live command example and exit",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.print_live_command:
        cmd = (
            "PYTHONPATH=src python -m trader_incubator.live "
            "--all-seasons --project-root ."
        )
        print(cmd)
        return 0

    project_root = Path(args.project_root).resolve()
    state_file = Path(args.state_file).resolve()
    codex_bin = str(args.codex_bin).strip() or _default_codex_bin(project_root)
    orch = Orchestrator(
        project_root=project_root,
        loop_timezone=args.timezone,
        poll_seconds=args.poll_seconds,
        state_file=state_file,
        dry_run=args.dry_run,
        codex_bin=codex_bin,
    )
    return orch.run(once=bool(args.once))


if __name__ == "__main__":
    raise SystemExit(main())
