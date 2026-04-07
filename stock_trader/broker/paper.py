"""
Paper Trading (모의 거래) 브로커
실거래 API 없이 전략을 실시간으로 테스트합니다.
"""
import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)


class PaperBroker:
    def __init__(self, initial_capital: float):
        self.capital = initial_capital
        self.positions: dict[str, int] = {}       # ticker → 보유 수량
        self.avg_prices: dict[str, float] = {}    # ticker → 평균 단가

    def buy(self, ticker: str, price: float, shares: int) -> bool:
        cost = price * shares
        if cost > self.capital:
            logger.warning(f"[{ticker}] 매수 실패: 잔고 부족 ({self.capital:,.0f} < {cost:,.0f})")
            return False
        self.capital -= cost
        prev = self.positions.get(ticker, 0)
        prev_avg = self.avg_prices.get(ticker, 0.0)
        new_shares = prev + shares
        self.avg_prices[ticker] = (prev * prev_avg + shares * price) / new_shares
        self.positions[ticker] = new_shares
        logger.info(f"[Paper] 매수 {ticker} {price:,.0f}원 x {shares}주 | 잔고 {self.capital:,.0f}원")
        return True

    def sell(self, ticker: str, price: float, shares: int | None = None) -> bool:
        held = self.positions.get(ticker, 0)
        if held == 0:
            logger.warning(f"[{ticker}] 매도 실패: 보유 없음")
            return False
        qty = shares or held
        proceeds = price * qty
        self.capital += proceeds
        self.positions[ticker] = held - qty
        if self.positions[ticker] == 0:
            del self.positions[ticker]
            del self.avg_prices[ticker]
        logger.info(f"[Paper] 매도 {ticker} {price:,.0f}원 x {qty}주 | 잔고 {self.capital:,.0f}원")
        return True

    def portfolio_value(self, prices: dict[str, float]) -> float:
        stock_value = sum(prices.get(t, 0) * q for t, q in self.positions.items())
        return self.capital + stock_value

    def status(self, prices: dict[str, float]) -> None:
        print(f"\n{'='*40}")
        print(f"  [Paper Broker] 포트폴리오 현황")
        print(f"{'='*40}")
        print(f"  현금: {self.capital:>15,.0f}원")
        for ticker, qty in self.positions.items():
            price = prices.get(ticker, 0)
            avg = self.avg_prices.get(ticker, 0)
            pnl_pct = (price - avg) / avg * 100 if avg else 0
            print(f"  {ticker}: {qty}주 @ {avg:,.0f}원 (현재 {price:,.0f}원, {pnl_pct:+.1f}%)")
        print(f"  총 평가금액: {self.portfolio_value(prices):>12,.0f}원")
        print(f"{'='*40}\n")
