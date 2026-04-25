"""
자동매매 봇 - 백그라운드 스레드로 실행
KIS API로 주문, pykrx로 데이터 수집
"""
import threading
import time
from collections import deque
from datetime import datetime, time as dtime
from dataclasses import dataclass, field

from broker.kis import KISBroker
from data.market_data import fetch_ohlcv
from strategy import get_strategy
from utils.logger import get_logger

logger = get_logger(__name__)

MARKET_OPEN = dtime(9, 0)
MARKET_CLOSE = dtime(15, 30)


@dataclass
class BotConfig:
    ticker: str
    strategy_name: str
    strategy_params: dict
    invest_amount: int        # 1회 투자금
    interval_sec: int = 300   # 신호 확인 주기 (초)


@dataclass
class BotState:
    running: bool = False
    config: BotConfig | None = None
    last_signal: str = "없음"
    last_checked: str = ""
    logs: deque = field(default_factory=lambda: deque(maxlen=100))
    error: str = ""


_state = BotState()
_lock = threading.Lock()
_thread: threading.Thread | None = None
_broker: KISBroker | None = None


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    with _lock:
        _state.logs.append(entry)
    logger.info(msg)


def _is_market_open() -> bool:
    now = datetime.now().time()
    return MARKET_OPEN <= now <= MARKET_CLOSE


def _run_loop(broker: KISBroker, config: BotConfig) -> None:
    strategy = get_strategy(config.strategy_name, config.strategy_params)
    _log(f"봇 시작 | 종목: {config.ticker} | 전략: {strategy} | 주기: {config.interval_sec}초")

    while True:
        with _lock:
            if not _state.running:
                break

        try:
            if not _is_market_open():
                _log("장외 시간 — 대기 중")
                time.sleep(60)
                continue

            today = datetime.now().strftime("%Y%m%d")
            df = fetch_ohlcv(config.ticker, "20230101", today)
            signals = strategy.generate_signals(df)
            sig = int(signals.iloc[-1])

            price_info = broker.get_price(config.ticker)
            price = price_info["price"]

            with _lock:
                _state.last_checked = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if sig == 1:
                qty = int(config.invest_amount / price)
                if qty > 0:
                    broker.buy(config.ticker, qty, 0)
                    _log(f"🟢 매수 | {config.ticker} {qty}주 @ {price:,}원")
                    with _lock:
                        _state.last_signal = "매수"
                else:
                    _log(f"⚠️ 매수 신호이나 투자금 부족 (현재가 {price:,}원)")

            elif sig == -1:
                balance = broker.get_balance()
                held = next((p["qty"] for p in balance["positions"] if p["ticker"] == config.ticker), 0)
                if held > 0:
                    broker.sell(config.ticker, held, 0)
                    _log(f"🔴 매도 | {config.ticker} {held}주 @ {price:,}원")
                    with _lock:
                        _state.last_signal = "매도"
                else:
                    _log(f"⏸ 매도 신호이나 보유 없음")
            else:
                _log(f"⏸ 신호 없음 | {config.ticker} 현재가 {price:,}원 (전일대비 {price_info['change_pct']:+.2f}%)")
                with _lock:
                    _state.last_signal = "없음"

        except Exception as e:
            _log(f"❌ 오류: {e}")
            with _lock:
                _state.error = str(e)
            time.sleep(10)
            continue

        time.sleep(config.interval_sec)

    _log("봇 종료")


def start(broker: KISBroker, config: BotConfig) -> None:
    global _thread, _broker
    with _lock:
        if _state.running:
            raise RuntimeError("봇이 이미 실행 중입니다.")
        _state.running = True
        _state.config = config
        _state.error = ""
        _state.logs.clear()
    _broker = broker
    _thread = threading.Thread(target=_run_loop, args=(broker, config), daemon=True)
    _thread.start()


def stop() -> None:
    with _lock:
        _state.running = False


def get_state() -> dict:
    with _lock:
        cfg = _state.config
        return {
            "running": _state.running,
            "last_signal": _state.last_signal,
            "last_checked": _state.last_checked,
            "error": _state.error,
            "logs": list(_state.logs),
            "config": {
                "ticker": cfg.ticker,
                "strategy": cfg.strategy_name,
                "invest_amount": cfg.invest_amount,
                "interval_sec": cfg.interval_sec,
            } if cfg else None,
        }
