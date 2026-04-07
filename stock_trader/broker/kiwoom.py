"""
키움증권 OpenAPI+ 브로커 (Windows 전용)

사전 준비:
  1. 키움증권 계좌 개설
  2. OpenAPI+ 설치: https://www3.kiwoom.com/nkw.templateFrameSet.do?m=m1408000000
  3. pip install PyQt5
  4. Windows 환경에서만 동작합니다.
"""
import sys
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QAxContainer import QAxWidget
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


class KiwoomBroker:
    """
    키움 OpenAPI+ 래퍼.
    실제 사용 전 반드시 모의투자로 먼저 테스트하세요.
    """

    def __init__(self, account_no: str, is_simulation: bool = True):
        if not _AVAILABLE:
            raise RuntimeError(
                "키움 API는 Windows + PyQt5 환경에서만 사용 가능합니다.\n"
                "pip install PyQt5  후 Windows에서 실행하세요."
            )
        if sys.platform != "win32":
            raise RuntimeError("키움 OpenAPI+는 Windows 전용입니다.")

        self.account_no = account_no
        self.is_simulation = is_simulation
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self._connected = False
        logger.info(f"키움 브로커 초기화 | 계좌: {account_no} | 모의: {is_simulation}")

    def login(self) -> None:
        """로그인 (팝업 창 발생)"""
        self._ocx.dynamicCall("CommConnect()")
        # 실제 구현에서는 OnEventConnect 이벤트 대기 필요
        logger.info("로그인 요청 완료 (팝업에서 인증 진행)")

    def get_balance(self) -> float:
        """예수금 조회 (TR: opw00001)"""
        # TR 요청 로직 구현 필요
        raise NotImplementedError("TR opw00001 구현 필요")

    def order_buy(self, ticker: str, price: int, quantity: int) -> str:
        """
        지정가 매수 주문

        Returns:
            주문번호
        """
        order_type = 1   # 신규매수
        hoga_type = "00" # 지정가
        ret = self._ocx.dynamicCall(
            "SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
            ["매수", "0101", self.account_no, order_type, ticker, quantity, price, hoga_type, ""]
        )
        if ret == 0:
            logger.info(f"[{ticker}] 매수 주문 성공: {price:,}원 x {quantity}주")
        else:
            logger.error(f"[{ticker}] 매수 주문 실패: 에러코드 {ret}")
        return str(ret)

    def order_sell(self, ticker: str, price: int, quantity: int) -> str:
        """지정가 매도 주문"""
        order_type = 2   # 신규매도
        hoga_type = "00"
        ret = self._ocx.dynamicCall(
            "SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
            ["매도", "0101", self.account_no, order_type, ticker, quantity, price, hoga_type, ""]
        )
        if ret == 0:
            logger.info(f"[{ticker}] 매도 주문 성공: {price:,}원 x {quantity}주")
        else:
            logger.error(f"[{ticker}] 매도 주문 실패: 에러코드 {ret}")
        return str(ret)
