from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    """모든 전략의 기본 클래스."""

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        매매 신호를 생성합니다.

        Returns:
            Series (index=날짜): 1=매수, -1=매도, 0=유지
        """
        ...

    def __repr__(self) -> str:
        return self.__class__.__name__
