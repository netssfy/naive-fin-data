from __future__ import annotations

from datetime import datetime
import random
from typing import Mapping

import pandas as pd

from exchange import TradingStrategy


class TraderProgram(TradingStrategy):
    """Test trader: submit one random market order every 5 minutes."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._rng = random.Random()

    def on_minute(self, event_time: datetime, latest_bars: Mapping[str, pd.Series]) -> None:
        if event_time.minute % 5 != 0:
            return

        available_symbols = [symbol for symbol in self.symbols if symbol.key in latest_bars]
        if not available_symbols:
            return

        symbol = self._rng.choice(available_symbols)
        side = self._rng.choice(["buy", "sell"])
        quantity = self._rng.choice([100, 200, 500])

        position = self.get_position(code=symbol.code, market=symbol.market, type_name=symbol.type_name)
        if side == "sell":
            if position <= 0:
                side = "buy"
            else:
                quantity = min(quantity, position)
                if quantity <= 0:
                    return

        self.place_market_order(
            code=symbol.code,
            side=side,
            quantity=quantity,
            market=symbol.market,
            type_name=symbol.type_name,
        )
