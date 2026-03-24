from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from trader import Trader


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


def discover_trader_tasks(project_root: Path, season_slugs: list[str]) -> list[TraderTask]:
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


def default_codex_bin(project_root: Path) -> str:
    local_name = "codex.cmd" if os.name == "nt" else "codex"
    candidate_bins = [
        project_root / "apps" / "web" / "node_modules" / ".bin",
        project_root / "src" / "trader_incubator" / "apps" / "web" / "node_modules" / ".bin",
    ]
    for local_bin in candidate_bins:
        local_path = local_bin / local_name
        if local_path.exists():
            return str(local_path)
    resolved = shutil.which("codex")
    if resolved:
        return resolved
    return "codex"


def _run_single_trader_research(
    task: TraderTask,
    project_root: Path,
    codex_bin: str,
    dry_run: bool,
) -> None:
    prompt = _build_research_prompt(task)
    command = [str(codex_bin).strip() or "codex", "exec", prompt]
    print(f"[RESEARCH] season={task.season_slug} trader={task.trader_slug}")
    rc = _run_command(command=command, cwd=project_root, dry_run=dry_run)
    if rc != 0:
        print(
            f"[RESEARCH][WARN] codex task failed season={task.season_slug} "
            f"trader={task.trader_slug} code={rc}"
        )


def run_season_trader_research(
    season_slug: str,
    project_root: Path,
    codex_bin: str,
    dry_run: bool = False,
) -> int:
    tasks = discover_trader_tasks(project_root=project_root, season_slugs=[season_slug])
    for task in tasks:
        _run_single_trader_research(task=task, project_root=project_root, codex_bin=codex_bin, dry_run=dry_run)
    return len(tasks)
