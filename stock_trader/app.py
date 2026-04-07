"""
자동 주식 거래 - Streamlit 웹 UI

실행:
  streamlit run app.py
"""
import sys
import math
from pathlib import Path

# 로컬 및 클라우드 모두 동작하도록 경로 설정
_root = Path(__file__).parent
sys.path.insert(0, str(_root))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data.market_data import fetch_ohlcv, get_ticker_name
from strategy import get_strategy
from backtest.engine import BacktestEngine, BacktestResult, Trade
from backtest.metrics import calc_metrics

# ── 페이지 설정 ──────────────────────────────────────────────
st.set_page_config(
    page_title="주식 자동매매 백테스트",
    page_icon="📈",
    layout="wide",
)

st.title("📈 주식 자동매매 백테스트")

# ── 사이드바: 설정 ────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 설정")

    st.subheader("종목")
    ticker_input = st.text_area(
        "종목코드 (줄바꿈으로 구분)",
        value="005930\n000660\n035420",
        height=100,
    )
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

# ── 메인: 실행 및 결과 ────────────────────────────────────────
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
        status.text(f"[{i+1}/{len(tickers)}] {ticker} {name} 처리 중...")
        progress.progress((i) / len(tickers), text=f"데이터 수집: {ticker} {name}")

        try:
            df = fetch_ohlcv(ticker, start_date, end_date)
            all_data[ticker] = df
            progress.progress((i + 0.5) / len(tickers), text=f"백테스트: {ticker} {name}")
            result = engine.run(ticker, df, strategy)
            results.append(result)
        except Exception as e:
            st.warning(f"[{ticker}] 실패: {e}")

    progress.progress(1.0, text="완료!")
    status.empty()

    if not results:
        st.error("백테스트 결과가 없습니다.")
        st.stop()

    # ── 결과 요약 테이블 ────────────────────────────────────────
    st.subheader("📊 결과 요약")
    rows = [calc_metrics(r, initial_capital) for r in results]
    df_summary = pd.DataFrame(rows).set_index("종목")

    def color_value(val):
        if isinstance(val, str) and val.startswith("-"):
            return "color: #ff4b4b"
        elif isinstance(val, str) and val.startswith("+") or (
            isinstance(val, str) and val not in ["0.00%", "0.00"] and not val.startswith("-")
            and any(c.isdigit() for c in val)
        ):
            return "color: #00c853"
        return ""

    st.dataframe(df_summary.style.applymap(color_value), use_container_width=True)

    # ── KPI 카드 ────────────────────────────────────────────────
    st.subheader("💰 종목별 최종 자산")
    cols = st.columns(len(results))
    for col, r in zip(cols, results):
        metrics = calc_metrics(r, initial_capital)
        final = r.equity_curve.iloc[-1]
        delta = final - initial_capital
        col.metric(
            label=f"{r.ticker} ({get_ticker_name(r.ticker)})",
            value=f"{final:,.0f}원",
            delta=f"{delta:+,.0f}원 ({metrics['총 수익률']})",
        )

    # ── 자산 곡선 ────────────────────────────────────────────────
    st.subheader("📉 자산 곡선 (Equity Curve)")
    fig = go.Figure()
    fig.add_hline(
        y=initial_capital,
        line_dash="dash",
        line_color="gray",
        annotation_text="초기자본",
    )
    for r in results:
        name = get_ticker_name(r.ticker)
        fig.add_trace(go.Scatter(
            x=r.equity_curve.index,
            y=r.equity_curve.values,
            mode="lines",
            name=f"{r.ticker} {name}",
            hovertemplate="%{x}<br>%{y:,.0f}원<extra></extra>",
        ))
    fig.update_layout(
        xaxis_title="날짜",
        yaxis_title="자산 (원)",
        hovermode="x unified",
        height=400,
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── 매매 내역 ────────────────────────────────────────────────
    st.subheader("🔄 매매 내역")
    tab_labels = [f"{r.ticker} ({get_ticker_name(r.ticker)})" for r in results]
    tabs = st.tabs(tab_labels)

    for tab, r in zip(tabs, results):
        with tab:
            if not r.trades:
                st.write("거래 없음")
                continue
            trade_rows = []
            for t in r.trades:
                trade_rows.append({
                    "매수일": t.entry_date.date(),
                    "매수가": f"{t.entry_price:,.0f}",
                    "매도일": t.exit_date.date() if t.exit_date else "-",
                    "매도가": f"{t.exit_price:,.0f}" if t.exit_price else "-",
                    "수량": t.shares,
                    "손익": f"{t.pnl:+,.0f}원",
                    "수익률": f"{t.return_pct:.2%}",
                })
            df_trades = pd.DataFrame(trade_rows)

            def highlight_pnl(row):
                color = "#2d4a2d" if row["손익"].startswith("+") else "#4a2d2d"
                return [f"background-color: {color}"] * len(row)

            st.dataframe(
                df_trades.style.apply(highlight_pnl, axis=1),
                use_container_width=True,
                hide_index=True,
            )

    # ── 캔들차트 ────────────────────────────────────────────────
    st.subheader("🕯️ 캔들차트 + 매매 신호")
    selected = st.selectbox("종목 선택", [r.ticker for r in results])
    r = next(x for x in results if x.ticker == selected)
    df_c = all_data[selected]

    fig2 = make_subplots(rows=2, cols=1, shared_xaxes=True,
                         row_heights=[0.75, 0.25], vertical_spacing=0.03)

    fig2.add_trace(go.Candlestick(
        x=df_c.index, open=df_c["open"], high=df_c["high"],
        low=df_c["low"], close=df_c["close"], name="캔들",
        increasing_line_color="#ff4b4b", decreasing_line_color="#4b9eff",
    ), row=1, col=1)

    # 매수/매도 마커
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

    fig2.update_layout(
        xaxis_rangeslider_visible=False,
        height=550,
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig2, use_container_width=True)

else:
    st.markdown("""
    ### 사용 방법
    1. 왼쪽 사이드바에서 **종목, 기간, 전략** 설정
    2. **▶ 백테스트 실행** 버튼 클릭
    3. 결과 테이블, 자산 곡선, 매매 내역, 캔들차트 확인

    ---
    **지원 전략**
    - `MA 골든크로스`: 단기/장기 이동평균 교차 시 매수/매도
    - `RSI`: 과매도 구간 매수, 과매수 구간 매도
    """)
