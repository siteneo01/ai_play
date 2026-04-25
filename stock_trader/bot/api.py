"""
FastAPI 서버 - 자동매매 봇 상태 API

Railway에서 실행: uvicorn bot.api:app --host 0.0.0.0 --port $PORT

환경변수:
  APP_KEY      KIS App Key
  APP_SECRET   KIS App Secret
  ACCOUNT_NO   계좌번호
  IS_MOCK      1=모의투자(기본), 0=실전투자
  BOT_TOKEN    API 인증 토큰 (임의 문자열)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from broker.kis import KISBroker
from bot import trader
from bot.trader import BotConfig

app = FastAPI(title="자동매매 봇 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_security = HTTPBearer()
_BOT_TOKEN = os.environ.get("BOT_TOKEN", "changeme")


def _auth(cred: HTTPAuthorizationCredentials = Depends(_security)):
    if cred.credentials != _BOT_TOKEN:
        raise HTTPException(status_code=401, detail="인증 실패")


def _get_broker() -> KISBroker:
    app_key = os.environ.get("APP_KEY", "")
    app_secret = os.environ.get("APP_SECRET", "")
    account_no = os.environ.get("ACCOUNT_NO", "")
    is_mock = os.environ.get("IS_MOCK", "1") == "1"
    if not app_key or not app_secret or not account_no:
        raise HTTPException(status_code=500, detail="환경변수 APP_KEY / APP_SECRET / ACCOUNT_NO 설정 필요")
    return KISBroker(app_key, app_secret, account_no, is_mock)


# ── 엔드포인트 ───────────────────────────────────────────────
@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/status", dependencies=[Depends(_auth)])
def status():
    state = trader.get_state()
    try:
        balance = _get_broker().get_balance()
    except Exception as e:
        balance = {"error": str(e)}
    return {"bot": state, "balance": balance}


class StartRequest(BaseModel):
    ticker: str
    strategy_name: str = "ma_crossover"
    strategy_params: dict = {"short_window": 5, "long_window": 20}
    invest_amount: int = 1_000_000
    interval_sec: int = 300


@app.post("/start", dependencies=[Depends(_auth)])
def start(req: StartRequest):
    broker = _get_broker()
    config = BotConfig(
        ticker=req.ticker,
        strategy_name=req.strategy_name,
        strategy_params=req.strategy_params,
        invest_amount=req.invest_amount,
        interval_sec=req.interval_sec,
    )
    try:
        trader.start(broker, config)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": f"봇 시작: {req.ticker}"}


@app.post("/stop", dependencies=[Depends(_auth)])
def stop():
    trader.stop()
    return {"message": "봇 중단 요청 완료"}
