from strategy.base import BaseStrategy
from strategy.ma_crossover import MACrossoverStrategy
from strategy.rsi_strategy import RSIStrategy

STRATEGIES = {
    "ma_crossover": MACrossoverStrategy,
    "rsi": RSIStrategy,
}


def get_strategy(name: str, params: dict) -> BaseStrategy:
    if name not in STRATEGIES:
        raise ValueError(f"알 수 없는 전략: {name}. 사용 가능: {list(STRATEGIES)}")
    return STRATEGIES[name](**params)
