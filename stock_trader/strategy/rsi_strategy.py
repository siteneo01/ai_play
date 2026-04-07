"""
RSI 과매수/과매도 전략
- RSI < oversold  → 매수
- RSI > overbought → 매도
"""
import pandas as pd
from strategy.base import BaseStrategy


class RSIStrategy(BaseStrategy):
    def __init__(self, period: int = 14, oversold: int = 30, overbought: int = 70, **_):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def _calc_rsi(self, close: pd.Series) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(self.period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.period).mean()
        rs = gain / loss.replace(0, float("inf"))
        return 100 - (100 / (1 + rs))

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        rsi = self._calc_rsi(df["close"])
        signal = pd.Series(0, index=df.index)
        signal[rsi < self.oversold] = 1    # 매수
        signal[rsi > self.overbought] = -1  # 매도
        # 연속 신호 제거: 상태 변화 시에만 신호 발생
        position = signal.replace(0, method="ffill").fillna(0)
        return position.diff().fillna(0).astype(int)

    def __repr__(self) -> str:
        return f"RSI(period={self.period}, oversold={self.oversold}, overbought={self.overbought})"
