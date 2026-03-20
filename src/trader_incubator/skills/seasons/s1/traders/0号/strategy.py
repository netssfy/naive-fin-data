from __future__ import annotations

from datetime import datetime
from typing import Mapping

import pandas as pd

from trader_incubator.exchange import TradingStrategy


class TraderProgram(TradingStrategy):
    """0号 — event-driven/swing/high-conviction strategy for season s1.

    风格：事件驱动 + 波段 + 高信念
    逻辑：
      - 用短期动量（5分钟涨幅）作为事件信号
      - 涨幅 > 1% 且持仓为 0 → 买入 100 股（高信念入场）
      - 跌幅 > 0.8% 且持仓 > 0 → 全部卖出（止损离场）
      - 每个标的独立判断
    """

    ENTRY_THRESHOLD = 0.01   # 1% 涨幅触发买入
    EXIT_THRESHOLD = -0.008  # 0.8% 跌幅触发止损
    POSITION_SIZE = 100      # 每次买入手数

    def on_pre_open(self, event_time: datetime) -> None:
        pass

    def on_minute(self, event_time: datetime, latest_bars: Mapping[str, pd.Series]) -> None:
        for symbol in self.symbols:
            bar = latest_bars.get(symbol.key)
            if bar is None:
                continue

            # 取最近 5 根 1m bar 计算短期动量
            hist = self.history(symbol.code, lookback=5, end_time=event_time, market=symbol.market)
            if len(hist) < 2:
                continue

            prev_close = float(hist.iloc[-2]["close"])
            curr_close = float(bar["close"])
            if prev_close <= 0:
                continue

            momentum = (curr_close - prev_close) / prev_close
            position = self.get_position(symbol.code, market=symbol.market)

            if momentum > self.ENTRY_THRESHOLD and position == 0:
                self.place_market_order(symbol.code, "buy", self.POSITION_SIZE, market=symbol.market)
                print(f"[{event_time}] 0号 BUY {symbol.code} momentum={momentum:.2%}")

            elif momentum < self.EXIT_THRESHOLD and position > 0:
                self.place_market_order(symbol.code, "sell", position, market=symbol.market)
                print(f"[{event_time}] 0号 SELL {symbol.code} momentum={momentum:.2%}")

    def on_post_close(self, event_time: datetime) -> None:
        print(f"[{event_time}] 0号 收盘复盘")
        for symbol in self.symbols:
            pos = self.get_position(symbol.code, market=symbol.market)
            print(f"  {symbol.code} 持仓: {pos}")
