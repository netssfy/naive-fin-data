from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class Market(str, Enum):
    CN_A = "A_SHARE"
    HK = "HK"
    US = "US"


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class SkillSpec:
    name: str
    skill_md_path: Path


@dataclass(frozen=True)
class SeasonConfig:
    season_id: str
    market: Market
    starts_at: datetime
    ends_at: datetime | None = None
    tradable_symbols: set[str] | None = None


@dataclass(frozen=True)
class TraderDefinition:
    trader_id: str
    name: str
    style: str
    creator_skill: SkillSpec
    trader_skill: SkillSpec
    program_entry: str


@dataclass(frozen=True)
class MarketTick:
    timestamp: datetime
    market_data: dict[str, Any]


@dataclass(frozen=True)
class TradeSignal:
    action: SignalAction
    symbol: str
    quantity: float
    reason: str = ""


@dataclass
class TradeRecord:
    timestamp: datetime
    trader_id: str
    signals: list[TradeSignal] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

