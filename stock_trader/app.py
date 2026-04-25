"""
자동 주식 거래 - Streamlit 웹 UI

실행:
  streamlit run app.py
"""
import sys
import time
import math
from pathlib import Path

_root = Path(__file__).parent
sys.path.insert(0, str(_root))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data.market_data import fetch_ohlcv, get_ticker_name
from strategy import get_strategy
from backtest.engine import BacktestEngine, BacktestResult
from backtest.metrics import calc_metrics

st.set_page_config(
    page_title="주식 자동매매",
    page_icon="📈",
    layout="wide",
)

st.title("📈 주식 자동매매 시스템")

tab_backtest, tab_live, tab_bot = st.tabs(["📊 백테스트", "🔴 모의/실전 투자", "🤖 봇 모니터링"])

# ════════════════════════════════════════════════════════════════
#  탭 1 : 백테스트
# ════════════════════════════════════════════════════════════════
with tab_backtest:
    with st.sidebar:
        st.header("⚙️ 백테스트 설정")

        st.subheader("종목")
        ticker_input = st.text_area("종목코드 (줄바꿈으로 구분)", value="005930\n000660\n035420", height=100)
        tickers = [t.strip() for t in ticker_input.strip().splitlines() if t.strip()]

        st.subheader("기간")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.text_input("시작일", value="20230101")
        with col2:
            end_date = st.text_input("종료일", value="20241231")

        st.subheader("전략")
        strategy_name = st.selectbox("전략 선택", ["ma_crossover", "rsi"])
        if strategy_name == "ma_crossover":
            short_window = st.slider("단기 MA", 3, 60, 5)
            long_window = st.slider("장기 MA", 10, 200, 20)
            strategy_params = {"short_window": short_window, "long_window": long_window}
        else:
            period = st.slider("RSI 기간", 5, 30, 14)
            oversold = st.slider("과매도 기준", 10, 40, 30)
            overbought = st.slider("과매수 기준", 60, 90, 70)
            strategy_params = {"period": period, "oversold": oversold, "overbought": overbought}

        st.subheader("자금/수수료")
        initial_capital = st.number_input("초기 자본 (원)", value=10_000_000, step=1_000_000)
        commission = st.number_input("수수료", value=0.00015, format="%.5f")
        slippage = st.number_input("슬리피지", value=0.001, format="%.4f")

        run_btn = st.button("▶ 백테스트 실행", type="primary", use_container_width=True)

    if run_btn:
        strategy = get_strategy(strategy_name, strategy_params)
        engine = BacktestEngine(initial_capital, commission, slippage)
        st.info(f"전략: **{strategy}** | 종목: {len(tickers)}개 | {start_date} ~ {end_date}")

        progress = st.progress(0, text="데이터 수집 중...")
        status = st.empty()
        results: list[BacktestResult] = []
        all_data: dict[str, pd.DataFrame] = {}

        for i, ticker in enumerate(tickers):
            name = get_ticker_name(ticker)
            progress.progress(i / len(tickers), text=f"수집 중: {ticker} {name}")
            try:
                df = fetch_ohlcv(ticker, start_date, end_date)
                all_data[ticker] = df
                progress.progress((i + 0.5) / len(tickers), text=f"백테스트: {ticker} {name}")
                results.append(engine.run(ticker, df, strategy))
            except Exception as e:
                st.warning(f"[{ticker}] 실패: {e}")

        progress.progress(1.0, text="완료!")
        status.empty()

        if not results:
            st.error("백테스트 결과가 없습니다.")
            st.stop()

        # 결과 테이블
        st.subheader("📊 결과 요약")
        rows = [calc_metrics(r, initial_capital) for r in results]
        df_summary = pd.DataFrame(rows).set_index("종목")

        def color_val(v):
            if isinstance(v, str) and v.startswith("-"):
                return "color:#ff4b4b"
            return "color:#00c853"

        st.dataframe(df_summary.style.applymap(color_val), use_container_width=True)

        # KPI 카드
        st.subheader("💰 최종 자산")
        cols = st.columns(len(results))
        for col, r in zip(cols, results):
            m = calc_metrics(r, initial_capital)
            delta = r.equity_curve.iloc[-1] - initial_capital
            col.metric(
                label=f"{r.ticker} ({get_ticker_name(r.ticker)})",
                value=f"{r.equity_curve.iloc[-1]:,.0f}원",
                delta=f"{delta:+,.0f}원 ({m['총 수익률']})",
            )

        # 자산 곡선
        st.subheader("📉 자산 곡선")
        fig = go.Figure()
        fig.add_hline(y=initial_capital, line_dash="dash", line_color="gray", annotation_text="초기자본")
        for r in results:
            fig.add_trace(go.Scatter(
                x=r.equity_curve.index, y=r.equity_curve.values,
                mode="lines", name=f"{r.ticker} {get_ticker_name(r.ticker)}",
                hovertemplate="%{x}<br>%{y:,.0f}원<extra></extra>",
            ))
        fig.update_layout(xaxis_title="날짜", yaxis_title="자산 (원)",
                          hovermode="x unified", height=400, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)

        # 매매 내역
        st.subheader("🔄 매매 내역")
        tabs = st.tabs([f"{r.ticker} ({get_ticker_name(r.ticker)})" for r in results])
        for tab, r in zip(tabs, results):
            with tab:
                if not r.trades:
                    st.write("거래 없음")
                    continue
                rows_t = [{
                    "매수일": t.entry_date.date(),
                    "매수가": f"{t.entry_price:,.0f}",
                    "매도일": t.exit_date.date() if t.exit_date else "-",
                    "매도가": f"{t.exit_price:,.0f}" if t.exit_price else "-",
                    "수량": t.shares,
                    "손익": f"{t.pnl:+,.0f}원",
                    "수익률": f"{t.return_pct:.2%}",
                } for t in r.trades]

                def hl(row):
                    c = "#2d4a2d" if row["손익"].startswith("+") else "#4a2d2d"
                    return [f"background-color:{c}"] * len(row)

                st.dataframe(pd.DataFrame(rows_t).style.apply(hl, axis=1),
                             use_container_width=True, hide_index=True)

        # 캔들차트
        st.subheader("🕯️ 캔들차트 + 매매 신호")
        sel = st.selectbox("종목 선택", [r.ticker for r in results])
        r = next(x for x in results if x.ticker == sel)
        df_c = all_data[sel]
        fig2 = make_subplots(rows=2, cols=1, shared_xaxes=True,
                             row_heights=[0.75, 0.25], vertical_spacing=0.03)
        fig2.add_trace(go.Candlestick(
            x=df_c.index, open=df_c["open"], high=df_c["high"],
            low=df_c["low"], close=df_c["close"], name="캔들",
            increasing_line_color="#ff4b4b", decreasing_line_color="#4b9eff",
        ), row=1, col=1)
        buys = [(t.entry_date, t.entry_price) for t in r.trades]
        sells = [(t.exit_date, t.exit_price) for t in r.trades if t.exit_date]
        if buys:
            fig2.add_trace(go.Scatter(
                x=[b[0] for b in buys], y=[b[1] for b in buys],
                mode="markers", marker=dict(symbol="triangle-up", size=12, color="#ff4b4b"),
                name="매수",
            ), row=1, col=1)
        if sells:
            fig2.add_trace(go.Scatter(
                x=[s[0] for s in sells], y=[s[1] for s in sells],
                mode="markers", marker=dict(symbol="triangle-down", size=12, color="#4b9eff"),
                name="매도",
            ), row=1, col=1)
        fig2.add_trace(go.Bar(
            x=df_c.index, y=df_c["volume"], name="거래량",
            marker_color="rgba(100,100,200,0.4)",
        ), row=2, col=1)
        fig2.update_layout(xaxis_rangeslider_visible=False, height=550,
                           margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig2, use_container_width=True)

    else:
        st.info("왼쪽 사이드바에서 설정 후 **▶ 백테스트 실행** 버튼을 클릭하세요.")


# ════════════════════════════════════════════════════════════════
#  탭 2 : 모의/실전 투자
# ════════════════════════════════════════════════════════════════
with tab_live:
    st.subheader("🔑 KIS API 연결")

    with st.expander("API 키 입력", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            app_key = st.text_input("App Key", type="password", placeholder="P-xxxxxxxxxxxxxxxxxxxxxxxx")
            account_no = st.text_input("계좌번호", placeholder="50123456-01")
        with col2:
            app_secret = st.text_input("App Secret", type="password", placeholder="xxxx...")
            is_mock = st.toggle("모의투자", value=True)

        connect_btn = st.button("🔌 연결", type="primary")

    if connect_btn:
        if not app_key or not app_secret or not account_no:
            st.error("App Key, App Secret, 계좌번호를 모두 입력해주세요.")
        else:
            try:
                from broker.kis import KISBroker
                with st.spinner("KIS API 연결 중..."):
                    broker = KISBroker(app_key, app_secret, account_no, is_mock)
                    balance = broker.get_balance()
                st.session_state["kis_broker"] = broker
                st.session_state["kis_balance"] = balance
                st.success(f"✅ {'모의' if is_mock else '실전'}투자 연결 완료!")
            except Exception as e:
                st.error(f"연결 실패: {e}")

    if "kis_broker" in st.session_state:
        broker = st.session_state["kis_broker"]
        balance = st.session_state["kis_balance"]

        # 잔고 현황
        st.subheader("💼 계좌 현황")
        k1, k2, k3 = st.columns(3)
        k1.metric("예수금", f"{balance['cash']:,.0f}원")
        k2.metric("총 평가금액", f"{balance['total_eval']:,.0f}원")
        k3.metric("평가손익", f"{balance['pnl']:+,.0f}원")

        # 보유 종목
        if balance["positions"]:
            st.subheader("📦 보유 종목")
            df_pos = pd.DataFrame(balance["positions"])
            df_pos.columns = ["종목코드", "종목명", "수량", "평균단가", "현재가", "손익(원)", "수익률(%)"]

            def hl_pnl(row):
                c = "#2d4a2d" if row["손익(원)"] >= 0 else "#4a2d2d"
                return [f"background-color:{c}"] * len(row)

            st.dataframe(df_pos.style.apply(hl_pnl, axis=1),
                         use_container_width=True, hide_index=True)
        else:
            st.info("보유 종목 없음")

        # 수동 주문
        st.subheader("📝 수동 주문")
        oc1, oc2, oc3, oc4 = st.columns(4)
        with oc1:
            order_ticker = st.text_input("종목코드", placeholder="005930")
        with oc2:
            order_side = st.selectbox("구분", ["매수", "매도"])
        with oc3:
            order_qty = st.number_input("수량", min_value=1, value=1)
        with oc4:
            order_price = st.number_input("가격 (0=시장가)", min_value=0, value=0)

        if st.button("주문 실행", type="primary"):
            if not order_ticker:
                st.error("종목코드를 입력하세요.")
            else:
                try:
                    if order_side == "매수":
                        order_no = broker.buy(order_ticker, order_qty, order_price)
                    else:
                        order_no = broker.sell(order_ticker, order_qty, order_price)
                    st.success(f"✅ 주문 완료 | 주문번호: {order_no}")
                    # 잔고 갱신
                    st.session_state["kis_balance"] = broker.get_balance()
                    st.rerun()
                except Exception as e:
                    st.error(f"주문 실패: {e}")

        # 자동매매
        st.subheader("🤖 자동매매")
        ac1, ac2 = st.columns(2)
        with ac1:
            auto_ticker = st.text_input("종목코드", placeholder="005930", key="auto_ticker")
            auto_strategy = st.selectbox("전략", ["ma_crossover", "rsi"], key="auto_strategy")
        with ac2:
            auto_capital = st.number_input("1회 투자금 (원)", value=1_000_000, step=100_000)
            auto_interval = st.selectbox("신호 확인 주기", ["1분", "5분", "10분", "30분"])

        interval_map = {"1분": 60, "5분": 300, "10분": 600, "30분": 1800}

        if st.button("🚀 자동매매 시작", type="primary"):
            if not auto_ticker:
                st.error("종목코드를 입력하세요.")
            else:
                st.warning(
                    f"**{auto_ticker}** 자동매매를 시작합니다.\n\n"
                    f"전략: {auto_strategy} | 주기: {auto_interval} | 투자금: {auto_capital:,}원\n\n"
                    "⚠️ 자동매매 실행 중에는 창을 닫지 마세요. 중단하려면 페이지를 새로고침하세요."
                )
                strategy = get_strategy(auto_strategy, {"short_window": 5, "long_window": 20,
                                                         "period": 14, "oversold": 30, "overbought": 70})
                log_area = st.empty()
                logs = []

                for _ in range(99999):
                    try:
                        today = __import__("datetime").datetime.now().strftime("%Y%m%d")
                        df = fetch_ohlcv(auto_ticker, "20230101", today)
                        signals = strategy.generate_signals(df)
                        sig = signals.iloc[-1]
                        price_info = broker.get_price(auto_ticker)
                        now_str = __import__("datetime").datetime.now().strftime("%H:%M:%S")
                        price = price_info["price"]

                        if sig == 1:
                            qty = int(auto_capital / price)
                            if qty > 0:
                                broker.buy(auto_ticker, qty, 0)
                                logs.append(f"[{now_str}] 🟢 매수 {qty}주 @ {price:,}원")
                        elif sig == -1:
                            for pos in broker.get_balance()["positions"]:
                                if pos["ticker"] == auto_ticker and pos["qty"] > 0:
                                    broker.sell(auto_ticker, pos["qty"], 0)
                                    logs.append(f"[{now_str}] 🔴 매도 {pos['qty']}주 @ {price:,}원")
                        else:
                            logs.append(f"[{now_str}] ⏸ 신호 없음 | 현재가 {price:,}원")

                        log_area.code("\n".join(logs[-20:]))
                        time.sleep(interval_map[auto_interval])

                    except Exception as e:
                        logs.append(f"오류: {e}")
                        log_area.code("\n".join(logs[-20:]))
                        time.sleep(10)
    else:
        st.info("API 키를 입력하고 **🔌 연결** 버튼을 클릭하세요.\n\n"
                "**API 키 발급:** https://apiportal.koreainvestment.com → 앱 등록 → 모의투자 선택")


# ════════════════════════════════════════════════════════════════
#  탭 3 : 봇 모니터링 (Railway 서버 연결)
# ════════════════════════════════════════════════════════════════
with tab_bot:
    import requests as _req

    st.subheader("🤖 Railway 봇 서버 모니터링")
    st.caption("Railway에 배포된 자동매매 봇의 상태를 실시간으로 확인하고 제어합니다.")

    with st.expander("🔌 서버 연결 설정", expanded=True):
        bc1, bc2 = st.columns(2)
        with bc1:
            bot_url = st.text_input("Railway 서버 URL", placeholder="https://xxxx.up.railway.app")
        with bc2:
            bot_token = st.text_input("Bot Token", type="password", placeholder="BOT_TOKEN 환경변수 값")

    def _bot_headers():
        return {"Authorization": f"Bearer {bot_token}"}

    def _bot_get(path):
        return _req.get(f"{bot_url}{path}", headers=_bot_headers(), timeout=10).json()

    def _bot_post(path, data=None):
        return _req.post(f"{bot_url}{path}", headers=_bot_headers(), json=data or {}, timeout=10).json()

    if bot_url and bot_token:
        # 상태 조회
        col_refresh, col_start, col_stop = st.columns([2, 1, 1])
        with col_refresh:
            refresh = st.button("🔄 상태 새로고침", use_container_width=True)

        if refresh or "bot_status" not in st.session_state:
            try:
                st.session_state["bot_status"] = _bot_get("/status")
            except Exception as e:
                st.error(f"서버 연결 실패: {e}")
                st.stop()

        status_data = st.session_state.get("bot_status", {})
        bot_info = status_data.get("bot", {})
        balance = status_data.get("balance", {})

        # 봇 상태
        is_running = bot_info.get("running", False)
        st.subheader("📡 봇 상태")
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("상태", "🟢 실행 중" if is_running else "⭕ 중단됨")
        s2.metric("마지막 신호", bot_info.get("last_signal", "-"))
        s3.metric("마지막 확인", bot_info.get("last_checked", "-"))
        s4.metric("오류", bot_info.get("error", "없음") or "없음")

        # 봇 제어
        st.subheader("🎮 봇 제어")
        ctrl1, ctrl2 = st.columns(2)
        with ctrl1:
            with st.form("start_form"):
                st.markdown("**봇 시작 설정**")
                f1, f2 = st.columns(2)
                with f1:
                    s_ticker = st.text_input("종목코드", value="005930")
                    s_strategy = st.selectbox("전략", ["ma_crossover", "rsi"])
                    s_amount = st.number_input("1회 투자금 (원)", value=1_000_000, step=100_000)
                with f2:
                    s_interval = st.selectbox("주기", ["60", "300", "600", "1800"],
                                              format_func=lambda x: {"60":"1분","300":"5분","600":"10분","1800":"30분"}[x])
                    if s_strategy == "ma_crossover":
                        s_short = st.number_input("단기 MA", value=5)
                        s_long = st.number_input("장기 MA", value=20)
                        s_params = {"short_window": int(s_short), "long_window": int(s_long)}
                    else:
                        s_period = st.number_input("RSI 기간", value=14)
                        s_params = {"period": int(s_period), "oversold": 30, "overbought": 70}

                if st.form_submit_button("🚀 봇 시작", type="primary", use_container_width=True):
                    try:
                        res = _bot_post("/start", {
                            "ticker": s_ticker,
                            "strategy_name": s_strategy,
                            "strategy_params": s_params,
                            "invest_amount": s_amount,
                            "interval_sec": int(s_interval),
                        })
                        st.success(res.get("message", "시작됨"))
                        st.rerun()
                    except Exception as e:
                        st.error(f"시작 실패: {e}")

        with ctrl2:
            st.markdown("**봇 중단**")
            if st.button("⏹ 봇 중단", type="secondary", use_container_width=True, disabled=not is_running):
                try:
                    res = _bot_post("/stop")
                    st.success(res.get("message", "중단 요청됨"))
                    st.rerun()
                except Exception as e:
                    st.error(f"중단 실패: {e}")

            # 현재 설정 표시
            if bot_info.get("config"):
                cfg = bot_info["config"]
                st.markdown("**현재 봇 설정**")
                st.json(cfg)

        # 계좌 현황
        if balance and "error" not in balance:
            st.subheader("💼 계좌 현황")
            b1, b2, b3 = st.columns(3)
            b1.metric("예수금", f"{balance.get('cash', 0):,.0f}원")
            b2.metric("총 평가금액", f"{balance.get('total_eval', 0):,.0f}원")
            b3.metric("평가손익", f"{balance.get('pnl', 0):+,.0f}원")

            if balance.get("positions"):
                st.subheader("📦 보유 종목")
                df_pos = pd.DataFrame(balance["positions"])
                df_pos.columns = ["종목코드", "종목명", "수량", "평균단가", "현재가", "손익(원)", "수익률(%)"]
                def hl_pos(row):
                    c = "#2d4a2d" if row["손익(원)"] >= 0 else "#4a2d2d"
                    return [f"background-color:{c}"] * len(row)
                st.dataframe(df_pos.style.apply(hl_pos, axis=1), use_container_width=True, hide_index=True)

        # 실시간 로그
        st.subheader("📋 봇 로그")
        logs = bot_info.get("logs", [])
        if logs:
            st.code("\n".join(reversed(logs[-30:])))
        else:
            st.caption("로그 없음")

        st.caption("⚡ 자동 새로고침하려면 위의 🔄 버튼을 클릭하세요.")
    else:
        st.info(
            "Railway 서버 URL과 Bot Token을 입력하세요.\n\n"
            "**Railway 배포 방법은 아래를 참고하세요.**"
        )
        st.markdown("""
        ### Railway 배포 순서
        1. **https://railway.app** 접속 → GitHub 로그인
        2. **New Project** → **Deploy from GitHub repo** → `siteneo01/ai_play` 선택
        3. **Root Directory** → `stock_trader` 설정
        4. **Variables** 탭에서 환경변수 추가:

        | 변수명 | 값 |
        |---|---|
        | `APP_KEY` | KIS App Key |
        | `APP_SECRET` | KIS App Secret |
        | `ACCOUNT_NO` | 계좌번호 |
        | `IS_MOCK` | `1` (모의투자) |
        | `BOT_TOKEN` | 임의 비밀 문자열 (예: `my-secret-token`) |

        5. 배포 완료 후 생성된 URL을 위 입력창에 입력
        """)
