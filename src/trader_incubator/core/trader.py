"""Trader data model for the trader incubator system."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from season import slugify, to_module_name


@dataclass
class Trader:
    """Represents a trader in a trading season.

    Attributes:
        trader:        Display name, also used as slug/ID, e.g. "Alpha Wolf" -> slug "alpha-wolf".
        season:        Display name of the season this trader belongs to.
        style:         Trading style, e.g. "trend-following/intraday/strict-stop-loss".
        program_entry: Python import path to strategy class, e.g. "path.to.module:ClassName".
        initial_capital: Initial cash assigned to this trader. None means inherit season default.
        symbols:       List of tradable symbol codes for this trader.
        created_at:    ISO-8601 datetime when this trader was created.
    """

    trader: str
    season: str
    style: str
    program_entry: str
    initial_capital: float | None = None
    symbols: list[str] = field(default_factory=list)
    created_at: str = ""

    @property
    def slug(self) -> str:
        return slugify(self.trader)

    @property
    def module_name(self) -> str:
        """Python-safe module name component derived from trader name."""
        return to_module_name(self.trader)

    @property
    def season_slug(self) -> str:
        return slugify(self.season)

    @property
    def season_module_name(self) -> str:
        return to_module_name(self.season)

    # ------------------------------------------------------------------ #
    # Serialisation                                                        #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> Trader:
        return cls(
            trader=data["trader"],
            season=data["season"],
            style=data["style"],
            program_entry=data["program_entry"],
            initial_capital=(
                float(data["initial_capital"]) if data.get("initial_capital") is not None else None
            ),
            symbols=data.get("symbols", []),
            created_at=data.get("created_at", ""),
        )

    @classmethod
    def from_json(cls, text: str) -> Trader:
        return cls.from_dict(json.loads(text))

    # ------------------------------------------------------------------ #
    # File I/O                                                             #
    # ------------------------------------------------------------------ #

    def save(self, project_root: Path | str = ".") -> Path:
        path = _trader_json_path(self.season_slug, self.slug, Path(project_root))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load(cls, season_slug: str, trader_slug: str, project_root: Path | str = ".") -> Trader:
        path = _trader_json_path(season_slug, trader_slug, Path(project_root))
        return cls.from_json(path.read_text(encoding="utf-8"))

    @classmethod
    def load_all(cls, season_slug: str, project_root: Path | str = ".") -> list[Trader]:
        traders_dir = (
            Path(project_root)
            / "src"
            / "trader_incubator"
            / "core"
            / "skills"
            / "seasons"
            / season_slug
            / "traders"
        )
        traders: list[Trader] = []
        if not traders_dir.exists():
            return traders
        for trader_json in sorted(traders_dir.glob("*/trader.json")):
            try:
                traders.append(cls.from_json(trader_json.read_text(encoding="utf-8")))
            except Exception:
                continue
        return traders


def _trader_json_path(season_slug: str, trader_slug: str, project_root: Path) -> Path:
    return (
        project_root
        / "src" / "trader_incubator" / "core" / "skills" / "seasons"
        / season_slug / "traders" / trader_slug / "trader.json"
    )
