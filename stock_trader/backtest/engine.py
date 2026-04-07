"""
백테스트 엔진
- 단일 종목 또는 다종목 순차 매매 시뮬레이션
- 수수료 및 슬리피지 반영
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from strategy.base import BaseStrategy
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp | None = None
    exit_price: float | None = None
    shares: int = 0

    @property
    def pnl(self) -> float:
        if self.exit_price is None:
            return 0.0
        return (self.exit_price - self.entry_price) * self.shares

    @property
    def return_pct(self) -> float:
        if self.exit_price is None or self.entry_price == 0:
            return 0.0
        return (self.exit_price - self.entry_price) / self.entry_price


@dataclass
class BacktestResult:
    ticker: str
    equity_curve: pd.Series
    trades: list[Trade] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, initial_capital: float, commission: float = 0.00015, slippage: float = 0.001):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

    def run(self, ticker: str, df: pd.DataFrame, strategy: BaseStrategy) -> BacktestResult:
        signals = strategy.generate_signals(df)
        capital = self.initial_capital
        shares = 0
        trades: list[Trade] = []
        current_trade: Trade | None = None
        equity = []

        for date, row in df.iterrows():
            sig = signals.get(date, 0)
            price = row["close"]

            if sig == 1 and shares == 0:  # 매수
                buy_price = price * (1 + self.slippage)
                shares = int(capital / buy_price)
                cost = shares * buy_price * (1 + self.commission)
                if shares > 0 and cost <= capital:
                    capital -= cost
                    current_trade = Trade(ticker, date, buy_price, shares=shares)
                    logger.debug(f"[{ticker}] 매수 {date.date()} {buy_price:,.0f}원 x {shares}주")

            elif sig == -1 and shares > 0:  # 매도
                sell_price = price * (1 - self.slippage)
                proceeds = shares * sell_price * (1 - self.commission)
                capital += proceeds
                if current_trade:
                    current_trade.exit_date = date
                    current_trade.exit_price = sell_price
                    trades.append(current_trade)
                    current_trade = None
                logger.debug(f"[{ticker}] 매도 {date.date()} {sell_price:,.0f}원")
                shares = 0

            equity.append(capital + shares * price)

        # 마지막 포지션 청산 (종가 기준)
        if shares > 0 and current_trade:
            last_price = df["close"].iloc[-1] * (1 - self.slippage)
            capital += shares * last_price * (1 - self.commission)
            current_trade.exit_date = df.index[-1]
            current_trade.exit_price = last_price
            trades.append(current_trade)
            equity[-1] = capital

        equity_curve = pd.Series(equity, index=df.index, name="equity")
        logger.info(f"[{ticker}] 백테스트 완료 | 거래 {len(trades)}회 | 최종 {capital:,.0f}원")
        return BacktestResult(ticker=ticker, equity_curve=equity_curve, trades=trades)
