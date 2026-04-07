"""
백테스트 성과 지표 계산 및 출력
"""
import math
import pandas as pd
import numpy as np
from tabulate import tabulate
from backtest.engine import BacktestResult


def calc_metrics(result: BacktestResult, initial_capital: float) -> dict:
    eq = result.equity_curve
    trades = result.trades

    total_return = (eq.iloc[-1] - initial_capital) / initial_capital
    days = (eq.index[-1] - eq.index[0]).days or 1
    cagr = (eq.iloc[-1] / initial_capital) ** (365 / days) - 1

    returns = eq.pct_change().dropna()
    sharpe = (returns.mean() / returns.std() * math.sqrt(252)) if returns.std() > 0 else 0.0

    rolling_max = eq.cummax()
    drawdown = (eq - rolling_max) / rolling_max
    max_dd = drawdown.min()

    win_trades = [t for t in trades if t.pnl > 0]
    win_rate = len(win_trades) / len(trades) if trades else 0.0
    avg_return = sum(t.return_pct for t in trades) / len(trades) if trades else 0.0

    return {
        "종목": result.ticker,
        "총 수익률": f"{total_return:.2%}",
        "CAGR": f"{cagr:.2%}",
        "샤프 비율": f"{sharpe:.2f}",
        "최대 낙폭 (MDD)": f"{max_dd:.2%}",
        "총 거래 수": len(trades),
        "승률": f"{win_rate:.2%}",
        "평균 수익률/거래": f"{avg_return:.2%}",
        "최종 자산": f"{eq.iloc[-1]:,.0f}원",
    }


def print_report(results: list[BacktestResult], initial_capital: float) -> None:
    rows = [calc_metrics(r, initial_capital) for r in results]
    print("\n" + "=" * 60)
    print("  백테스트 결과 요약")
    print("=" * 60)
    print(tabulate(rows, headers="keys", tablefmt="rounded_outline", numalign="right"))
    print()


def plot_equity(results: list[BacktestResult], initial_capital: float) -> None:
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.rcParams["font.family"] = "AppleGothic"  # macOS
        matplotlib.rcParams["axes.unicode_minus"] = False

        fig, ax = plt.subplots(figsize=(12, 5))
        ax.axhline(initial_capital, color="gray", linestyle="--", linewidth=0.8, label="초기자본")
        for r in results:
            ax.plot(r.equity_curve.index, r.equity_curve, label=r.ticker)
        ax.set_title("자산 곡선 (Equity Curve)")
        ax.set_ylabel("자산 (원)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig("equity_curve.png", dpi=150)
        print("차트 저장: equity_curve.png")
        plt.show()
    except Exception as e:
        print(f"차트 생성 실패: {e}")
