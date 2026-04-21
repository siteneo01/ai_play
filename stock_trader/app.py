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

tab_backtest, tab_live = st.tabs(["📊 백테스트", "🔴 모의/실전 투자"])

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
