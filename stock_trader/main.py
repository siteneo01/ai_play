"""
자동 주식 거래 프로그램 - 메인 진입점

사용법:
  # 백테스트
  python main.py --mode backtest

  # Paper Trading (실시간 모의)
  python main.py --mode paper

  # 키움 실거래 (Windows 전용)
  python main.py --mode live
"""
import argparse
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data.market_data import fetch_multiple, get_ticker_name
from strategy import get_strategy
from backtest.engine import BacktestEngine
from backtest.metrics import print_report, plot_equity
from utils.logger import get_logger

logger = get_logger("main")


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_backtest(cfg: dict) -> None:
    logger.info("=== 백테스트 시작 ===")
    uni = cfg["universe"]
    bt_cfg = cfg["backtest"]
    strat_cfg = cfg["strategy"]

    strategy = get_strategy(strat_cfg["name"], strat_cfg.get("params", {}))
    logger.info(f"전략: {strategy}")

    data = fetch_multiple(uni["tickers"], uni["start_date"], uni["end_date"])
    if not data:
        logger.error("데이터 수집 실패")
        return

    engine = BacktestEngine(
        initial_capital=bt_cfg["initial_capital"],
        commission=bt_cfg["commission"],
        slippage=bt_cfg["slippage"],
    )

    results = []
    for ticker, df in data.items():
        name = get_ticker_name(ticker)
        logger.info(f"[{ticker}] {name} 백테스트 중...")
        result = engine.run(ticker, df, strategy)
        results.append(result)

    print_report(results, bt_cfg["initial_capital"])
    plot_equity(results, bt_cfg["initial_capital"])


def run_paper(cfg: dict) -> None:
    """Paper Trading - 실시간 신호 출력 (pykrx는 장중 실시간 미지원, 1분 단위 폴링)"""
    import time
    from datetime import datetime, time as dtime
    from data.market_data import fetch_ohlcv
    from broker.paper import PaperBroker

    uni = cfg["universe"]
    strat_cfg = cfg["strategy"]
    strategy = get_strategy(strat_cfg["name"], strat_cfg.get("params", {}))
    broker = PaperBroker(cfg["backtest"]["initial_capital"])

    logger.info("=== Paper Trading 시작 (Ctrl+C로 종료) ===")
    MARKET_OPEN = dtime(9, 0)
    MARKET_CLOSE = dtime(15, 30)

    try:
        while True:
            now = datetime.now().time()
            if not (MARKET_OPEN <= now <= MARKET_CLOSE):
                logger.info("장외 시간. 30분 대기...")
                time.sleep(1800)
                continue

            today = datetime.now().strftime("%Y%m%d")
            prices = {}
            for ticker in uni["tickers"]:
                try:
                    df = fetch_ohlcv("20230101", today, ticker)
                    if df.empty:
                        continue
                    prices[ticker] = df["close"].iloc[-1]
                    signals = strategy.generate_signals(df)
                    sig = signals.iloc[-1]

                    if sig == 1:
                        price = prices[ticker]
                        shares = int(broker.capital * 0.3 / price)  # 자본의 30% 매수
                        broker.buy(ticker, price, shares)
                    elif sig == -1:
                        broker.sell(ticker, prices[ticker])
                except Exception as e:
                    logger.warning(f"[{ticker}] 오류: {e}")

            broker.status(prices)
            time.sleep(60)  # 1분 대기

    except KeyboardInterrupt:
        logger.info("Paper Trading 종료")


def run_live(cfg: dict) -> None:
    from broker.kiwoom import KiwoomBroker
    kw_cfg = cfg.get("kiwoom", {})
    broker = KiwoomBroker(
        account_no=kw_cfg.get("account_no", ""),
        is_simulation=kw_cfg.get("is_simulation", True),
    )
    broker.login()
    logger.info("키움 실거래 모드 시작 (구현 확장 필요)")


def main() -> None:
    parser = argparse.ArgumentParser(description="자동 주식 거래 프로그램")
    parser.add_argument("--mode", choices=["backtest", "paper", "live"], default="backtest")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.mode == "backtest":
        run_backtest(cfg)
    elif args.mode == "paper":
        run_paper(cfg)
    elif args.mode == "live":
        run_live(cfg)


if __name__ == "__main__":
    main()
