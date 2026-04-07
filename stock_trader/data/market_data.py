"""
pykrx를 이용한 국내 주식 OHLCV 데이터 수집
키움 API 없이 KRX에서 직접 가져옵니다 (백테스트용).
"""
import pandas as pd
from pykrx import stock
from utils.logger import get_logger

logger = get_logger(__name__)


def fetch_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    KRX에서 일봉 데이터를 가져옵니다.

    Args:
        ticker: 종목코드 (예: "005930")
        start:  시작일 "YYYYMMDD"
        end:    종료일 "YYYYMMDD"

    Returns:
        columns: [open, high, low, close, volume]
        index:   DatetimeIndex
    """
    logger.info(f"[{ticker}] 데이터 수집: {start} ~ {end}")
    df = stock.get_market_ohlcv_by_date(start, end, ticker)
    if df.empty:
        raise ValueError(f"데이터 없음: {ticker} ({start}~{end})")
    df.index = pd.to_datetime(df.index)
    df.columns = ["open", "high", "low", "close", "volume", "trade_value", "change_pct"]
    return df[["open", "high", "low", "close", "volume"]]


def fetch_multiple(tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """여러 종목 데이터를 딕셔너리로 반환합니다."""
    result = {}
    for ticker in tickers:
        try:
            result[ticker] = fetch_ohlcv(ticker, start, end)
        except Exception as e:
            logger.warning(f"[{ticker}] 수집 실패: {e}")
    return result


def get_ticker_name(ticker: str) -> str:
    """종목코드 → 종목명"""
    try:
        return stock.get_market_ticker_name(ticker)
    except Exception:
        return ticker
