"""
이동평균 골든크로스/데드크로스 전략
- 단기 MA > 장기 MA 전환 → 매수 (골든크로스)
- 단기 MA < 장기 MA 전환 → 매도 (데드크로스)
"""
import pandas as pd
from strategy.base import BaseStrategy


class MACrossoverStrategy(BaseStrategy):
    def __init__(self, short_window: int = 5, long_window: int = 20, **_):
        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        short_ma = df["close"].rolling(self.short_window).mean()
        long_ma = df["close"].rolling(self.long_window).mean()

        position = (short_ma > long_ma).astype(int)          # 1=보유, 0=미보유
        signal = position.diff().fillna(0).astype(int)        # +1=매수, -1=매도
        return signal

    def __repr__(self) -> str:
        return f"MACrossover(short={self.short_window}, long={self.long_window})"
