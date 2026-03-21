"""Season data model for the trader incubator system."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


def slugify(value: str) -> str:
    """Convert a display name to a filesystem-safe slug, e.g. 'Season 1' -> 'season-1'.

    Chinese characters are preserved as-is (valid on modern filesystems).
    ASCII letters are lowercased; spaces/underscores become hyphens.
    """
    value = value.strip()
    # lowercase only ASCII letters
    value = re.sub(r"[A-Z]", lambda m: m.group().lower(), value)
    value = re.sub(r"[\s_]+", "-", value)
    # keep word chars (including CJK) and hyphens, strip the rest
    value = re.sub(r"[^\w\-]", "", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def to_module_name(value: str) -> str:
    """Convert a display name to a valid Python module name component.

    Python 3 supports Unicode identifiers, so Chinese characters are kept.
    Spaces and hyphens become underscores.
    e.g. '江潮生' -> '江潮生', 'Alpha Wolf' -> 'alpha_wolf', 'Season 1' -> 's1'
    """
    result = value.strip()
    result = re.sub(r"[\s\-]+", "_", result)
    # remove chars that are not word chars (includes unicode letters/digits)
    result = re.sub(r"[^\w]", "", result)
    # lowercase ASCII portion
    result = re.sub(r"[A-Z]", lambda m: m.group().lower(), result)
    return result or "trader"


@dataclass
class SeasonTraderRef:
    """Lightweight reference to a trader stored in the season roster.

    Attributes:
        trader:        Display name (also used as slug/ID), e.g. "Alpha Wolf".
        style:         Trading style description.
        program_entry: Python import path to strategy class.
    """

    trader: str
    style: str
    program_entry: str

    @property
    def slug(self) -> str:
        return slugify(self.trader)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SeasonTraderRef:
        return cls(
            trader=data["trader"],
            style=data["style"],
            program_entry=data["program_entry"],
        )


@dataclass
class Season:
    """Represents a trading season.

    Attributes:
        season:       Display name, also used as slug/ID, e.g. "Season 1" -> slug "season-1".
        market:       Trading market: "A_SHARE" | "HK" | "US".
        start_date:   Season start date (ISO-8601, e.g. "2026-01-01").
        end_date:     Season end date (ISO-8601). None means open-ended.
        initial_capital: Initial cash assigned to each trader in this season.
        symbol_pool:  Allowed stock codes. Empty list means all market symbols allowed.
        traders:      Roster of traders registered in this season.
        created_at:   ISO-8601 datetime when this season was created.
    """

    season: str
    market: str
    start_date: str
    end_date: Optional[str] = None
    initial_capital: float = 1_000_000.0
    symbol_pool: list[str] = field(default_factory=list)
    traders: list[SeasonTraderRef] = field(default_factory=list)
    created_at: str = ""

    @property
    def slug(self) -> str:
        return slugify(self.season)

    # ------------------------------------------------------------------ #
    # Serialisation                                                        #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> Season:
        return cls(
            season=data["season"],
            market=data["market"],
            start_date=data["start_date"],
            end_date=data.get("end_date"),
            initial_capital=float(data.get("initial_capital", 1_000_000.0)),
            symbol_pool=data.get("symbol_pool", []),
            traders=[SeasonTraderRef.from_dict(t) for t in data.get("traders", [])],
            created_at=data.get("created_at", ""),
        )

    @classmethod
    def from_json(cls, text: str) -> Season:
        return cls.from_dict(json.loads(text))

    def add_trader(self, ref: SeasonTraderRef) -> None:
        """Add or update a trader reference in the roster (keyed by slug)."""
        for i, existing in enumerate(self.traders):
            if existing.slug == ref.slug:
                self.traders[i] = ref
                return
        self.traders.append(ref)

    # ------------------------------------------------------------------ #
    # File I/O                                                             #
    # ------------------------------------------------------------------ #

    def save(self, project_root: Path | str = ".") -> Path:
        path = _season_json_path(self.slug, Path(project_root))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load(cls, season_slug: str, project_root: Path | str = ".") -> Season:
        path = _season_json_path(season_slug, Path(project_root))
        return cls.from_json(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @property
    def is_open_ended(self) -> bool:
        return self.end_date is None

    def allows_symbol(self, code: str) -> bool:
        if not self.symbol_pool:
            return True
        return code in self.symbol_pool


def _season_json_path(season_slug: str, project_root: Path) -> Path:
    return project_root / "src" / "trader_incubator" / "skills" / "seasons" / season_slug / "season.json"
