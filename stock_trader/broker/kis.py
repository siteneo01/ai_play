"""
한국투자증권 KIS Developers REST API 브로커

모의투자:  base_url = https://openapivts.koreainvestment.com:29443
실전투자:  base_url = https://openapi.koreainvestment.com:9443
"""
import time
import requests
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)

_MOCK_URL = "https://openapivts.koreainvestment.com:29443"
_REAL_URL = "https://openapi.koreainvestment.com:9443"


class KISBroker:
    def __init__(self, app_key: str, app_secret: str, account_no: str, is_mock: bool = True):
        """
        Args:
            app_key:    KIS Developers App Key
            app_secret: KIS Developers App Secret
            account_no: 계좌번호 (예: "50123456-01")
            is_mock:    True=모의투자, False=실전투자
        """
        self.app_key = app_key
        self.app_secret = app_secret
        # 계좌번호를 앞 8자리 / 뒤 2자리로 분리
        no = account_no.replace("-", "")
        self.account_no = no[:8]
        self.account_code = no[8:] if len(no) > 8 else "01"
        self.is_mock = is_mock
        self.base_url = _MOCK_URL if is_mock else _REAL_URL

        self._token: str | None = None
        self._token_expires: datetime = datetime.min

        logger.info(f"KIS 브로커 초기화 | {'모의' if is_mock else '실전'}투자 | 계좌: {self.account_no}")

    # ── 인증 ────────────────────────────────────────────────────
    def _get_token(self) -> str:
        if self._token and datetime.now() < self._token_expires:
            return self._token

        url = f"{self.base_url}/oauth2/tokenP"
        resp = requests.post(url, json={
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = datetime.now() + timedelta(hours=23)
        logger.info("KIS 액세스 토큰 발급 완료")
        return self._token

    def _headers(self, tr_id: str) -> dict:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._get_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    # ── 시세 조회 ────────────────────────────────────────────────
    def get_price(self, ticker: str) -> dict:
        """현재가 조회"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        resp = requests.get(url, headers=self._headers("FHKST01010100"), params={
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": ticker,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"시세 조회 실패: {data.get('msg1')}")
        out = data["output"]
        return {
            "ticker": ticker,
            "price": int(out["stck_prpr"]),       # 현재가
            "open": int(out["stck_oprc"]),         # 시가
            "high": int(out["stck_hgpr"]),         # 고가
            "low": int(out["stck_lwpr"]),          # 저가
            "volume": int(out["acml_vol"]),         # 누적거래량
            "change_pct": float(out["prdy_ctrt"]), # 전일대비율
        }

    # ── 잔고 조회 ────────────────────────────────────────────────
    def get_balance(self) -> dict:
        """예수금 및 보유 종목 조회"""
        tr_id = "VTTC8434R" if self.is_mock else "TTTC8434R"
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        resp = requests.get(url, headers=self._headers(tr_id), params={
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_code,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"잔고 조회 실패: {data.get('msg1')}")

        summary = data["output2"][0] if data.get("output2") else {}
        positions = []
        for item in data.get("output1", []):
            qty = int(item.get("hldg_qty", 0))
            if qty > 0:
                positions.append({
                    "ticker": item["pdno"],
                    "name": item["prdt_name"],
                    "qty": qty,
                    "avg_price": float(item["pchs_avg_pric"]),
                    "current_price": int(item["prpr"]),
                    "pnl": float(item["evlu_pfls_amt"]),
                    "pnl_pct": float(item["evlu_pfls_rt"]),
                })

        return {
            "cash": int(summary.get("dnca_tot_amt", 0)),           # 예수금 총액
            "total_eval": int(summary.get("tot_evlu_amt", 0)),      # 총 평가금액
            "pnl": int(summary.get("evlu_pfls_smtl_amt", 0)),       # 평가손익 합계
            "positions": positions,
        }

    # ── 주문 ─────────────────────────────────────────────────────
    def _order(self, ticker: str, side: str, qty: int, price: int, order_type: str = "00") -> str:
        """
        Args:
            side:       "BUY" or "SELL"
            order_type: "00"=지정가, "01"=시장가
        Returns:
            주문번호
        """
        if side == "BUY":
            tr_id = "VTTC0802U" if self.is_mock else "TTTC0802U"
        else:
            tr_id = "VTTC0801U" if self.is_mock else "TTTC0801U"

        resp = requests.post(
            f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash",
            headers=self._headers(tr_id),
            json={
                "CANO": self.account_no,
                "ACNT_PRDT_CD": self.account_code,
                "PDNO": ticker,
                "ORD_DVSN": order_type,
                "ORD_QTY": str(qty),
                "ORD_UNPR": str(price),
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"주문 실패: {data.get('msg1')}")
        order_no = data["output"]["KRX_FWDG_ORD_ORGNO"]
        logger.info(f"[{ticker}] {side} {qty}주 @ {price:,}원 | 주문번호: {order_no}")
        return order_no

    def buy(self, ticker: str, qty: int, price: int = 0) -> str:
        """매수 주문 (price=0이면 시장가)"""
        order_type = "01" if price == 0 else "00"
        return self._order(ticker, "BUY", qty, price, order_type)

    def sell(self, ticker: str, qty: int, price: int = 0) -> str:
        """매도 주문 (price=0이면 시장가)"""
        order_type = "01" if price == 0 else "00"
        return self._order(ticker, "SELL", qty, price, order_type)

    # ── 미체결 조회 ──────────────────────────────────────────────
    def get_pending_orders(self) -> list[dict]:
        """미체결 주문 목록"""
        tr_id = "VTTC8036R" if self.is_mock else "TTTC8036R"
        resp = requests.get(
            f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl",
            headers=self._headers(tr_id),
            params={
                "CANO": self.account_no,
                "ACNT_PRDT_CD": self.account_code,
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
                "INQR_DVSN_1": "0",
                "INQR_DVSN_2": "0",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "order_no": o["odno"],
                "ticker": o["pdno"],
                "name": o["prdt_name"],
                "side": "BUY" if o["sll_buy_dvsn_cd"] == "02" else "SELL",
                "qty": int(o["ord_qty"]),
                "price": int(o["ord_unpr"]),
                "filled": int(o["tot_ccld_qty"]),
            }
            for o in data.get("output", [])
        ]
