from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from huntbot.auto_state import AUTO_STATE_PATH
from huntbot.config import LOG_DIR, load_environment
from huntbot.dashboard_collector import DashboardCollector, inspect_runtime
from huntbot.dashboard_metrics import calculate_performance
from huntbot.dashboard_store import DashboardStore
from huntbot.upbit_client import UpbitClient


DASHBOARD_DB_PATH = Path("data/dashboard/huntbot-dashboard.sqlite3")
AUTO_LOG_PATH = LOG_DIR / "huntbot-auto.log"


def next_action_text(phase: str) -> str:
    return {
        "buy_1": "완료 5분봉 RSI 45 이하: 가용 KRW의 50% 매수",
        "buy_2": "RSI 40 이하: 남은 KRW 매수 / RSI 60 이상: HUNT 50% 매도",
        "sell_1": "완료 5분봉 RSI 60 이상: HUNT 50% 매도",
        "sell_2": "완료 5분봉 RSI 65 이상: 남은 HUNT 매도",
        "emergency_halt": "급락 보호 발동으로 자동매매 중단 상태",
    }.get(phase, "상태를 확인할 수 없습니다")


def chart_domain(
    values: list[float],
    *,
    padding_ratio: float = 0.1,
    fallback: tuple[float, float] = (0, 1),
) -> tuple[float, float]:
    if not values:
        return fallback
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        padding = max(abs(minimum) * 0.01, 1.0)
    else:
        padding = (maximum - minimum) * padding_ratio
    return minimum - padding, maximum + padding


def main() -> None:
    import altair as alt
    import pandas as pd
    import streamlit as st

    load_environment()
    st.set_page_config(
        page_title="HUNT 자동매매 운영 대시보드",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _apply_style(st)
    store = DashboardStore(DASHBOARD_DB_PATH)
    collector = DashboardCollector(client=UpbitClient(), store=store)

    st.title("HUNT 자동매매 운영 대시보드")
    st.caption("읽기 전용 · KRW-HUNT · localhost 전용")
    view = st.segmented_control(
        "보기",
        ["거래 및 성과", "계산 기준"],
        default="거래 및 성과",
        label_visibility="collapsed",
    )
    refresh = st.button("새로고침", type="primary")
    if refresh or "dashboard_data" not in st.session_state:
        st.session_state.dashboard_data = _collect_dashboard_data(collector, store)

    data = st.session_state.dashboard_data
    runtime = data["runtime"]
    collection = data["collection"]
    snapshot = collection["snapshot"]
    orders = data["orders"]
    snapshots = data["snapshots"]
    candles = data["candles"]
    performance = data["performance"]

    _render_freshness(st, runtime, collection, store)
    _render_current_status(st, runtime, snapshot)
    if data["sync_error"]:
        st.warning(
            f"주문 동기화 실패: 마지막 정상 거래 데이터를 표시합니다. "
            f"{data['sync_error']}"
        )
    elif data["sync_warning"]:
        st.info(
            "종료 주문 목록 권한을 사용할 수 없어 로컬 로그의 UUID로 "
            "주문 상세를 동기화했습니다."
        )

    if view == "거래 및 성과":
        _render_performance(st, performance)
        _render_trade_history(st, pd, orders)
        _render_charts(st, alt, pd, orders, candles, snapshots, performance)
    else:
        _render_methodology(st, performance)


def _collect_dashboard_data(collector, store: DashboardStore) -> dict:
    now = datetime.now(timezone.utc)
    runtime = inspect_runtime(
        state_path=AUTO_STATE_PATH,
        log_path=AUTO_LOG_PATH,
        now=now,
    )
    sync_error = None
    try:
        collector.sync_orders(now=now, log_path=AUTO_LOG_PATH)
    except Exception as exc:
        sync_error = f"{type(exc).__name__}: {exc}"
        store.set_meta("last_error", sync_error)
    collection = collector.collect_market_snapshot(now=now)
    snapshot = collection["snapshot"]
    orders = store.list_orders(newest_first=True)
    snapshots = store.list_account_snapshots()
    candles = store.list_candles()
    performance = calculate_performance(
        list(reversed(orders)),
        current_hunt=snapshot["hunt_balance"] if snapshot else Decimal("0"),
        average_buy_price=(
            snapshot["average_buy_price"] if snapshot else Decimal("0")
        ),
        best_bid=snapshot["best_bid"] if snapshot else Decimal("0"),
        account_values=[
            (item["collected_at"], item["account_value"])
            for item in snapshots
        ],
    )
    return {
        "runtime": runtime,
        "collection": collection,
        "orders": orders,
        "snapshots": snapshots,
        "candles": candles,
        "performance": performance,
        "sync_error": sync_error,
        "sync_warning": store.get_meta("last_order_sync_warning"),
    }


def _render_freshness(st, runtime: dict, collection: dict, store: DashboardStore) -> None:
    snapshot = collection["snapshot"]
    collected_at = snapshot["collected_at"] if snapshot else None
    freshness = _format_kst(collected_at) if collected_at else "수집 데이터 없음"
    stale = " · STALE" if collection["stale"] else ""
    st.markdown(
        f'<div class="status-line"><strong>데이터 최신</strong> '
        f"{freshness}{stale}</div>",
        unsafe_allow_html=True,
    )
    error = collection["error"] or store.get_meta("last_error")
    if collection["stale"]:
        st.warning(f"Upbit 조회 실패로 마지막 정상 데이터를 표시합니다. {error}")


def _render_current_status(st, runtime: dict, snapshot: dict | None) -> None:
    st.subheader("현재 상태")
    values = st.columns(4)
    values[0].metric("Phase", runtime["phase"])
    values[1].metric(
        "HUNT 잔고",
        _number(snapshot, "hunt_balance", 4),
        help="괄호 안 금액은 현재 최우선 매수호가 기준 평가액입니다.",
    )
    values[1].caption(
        f"평가액 {_hunt_value(snapshot)}"
    )
    values[2].metric("KRW 잔고", _number(snapshot, "krw_balance", 0))
    values[3].markdown(
        f"**다음 행동 조건**  \n{next_action_text(runtime['phase'])}"
    )


def _render_performance(st, summary) -> None:
    st.subheader("성과 요약")
    row1 = st.columns(4)
    row1[0].metric("누적 매수", _krw(summary.cumulative_buy))
    row1[1].metric("누적 매도", _krw(summary.cumulative_sell))
    row1[2].metric(
        "실현손익 (매도 완료)",
        _krw(summary.realized_pnl),
        help="이미 매도해 확정된 손익입니다.",
    )
    row1[3].metric("현재 평가 손익", _krw(summary.unrealized_pnl))
    row2 = st.columns(4)
    row2[0].metric(
        "총손익 (실현+보유 평가)",
        _krw(summary.total_pnl),
        help="실현손익과 아직 보유 중인 HUNT의 평가손익을 합한 값입니다.",
    )
    row2[1].metric(
        "수익률",
        f"{summary.return_pct:.2f}%" if summary.return_pct is not None else "-",
    )
    row2[2].metric("총 수수료", _krw(summary.total_fees))
    row2[3].metric("매수 / 매도 횟수", f"{summary.buy_count} / {summary.sell_count}")
    row3 = st.columns(3)
    row3[0].metric("평균 매수가", _optional_krw(summary.average_buy_price))
    row3[1].metric("평균 매도가", _optional_krw(summary.average_sell_price))
    row3[2].metric(
        "최대 낙폭",
        f"{summary.max_drawdown_pct:.2f}%"
        if summary.max_drawdown_pct is not None
        else "데이터 부족",
    )
    if summary.is_partial:
        st.warning(
            "수집된 매수보다 매도 수량이 많아 실현손익은 부분 집계입니다. "
            f"원가 미확정 수량: {summary.unmatched_sell_quantity}"
        )
    st.caption(
        "실현손익은 이미 매도해서 확정된 금액이고, 총손익은 실현손익에 "
        "현재 보유 HUNT의 평가손익을 더한 금액입니다."
    )


def _render_trade_history(st, pd, orders: list[dict]) -> None:
    st.subheader("거래 내역")
    actions = ["전체", "buy_1", "buy_2", "sell_1", "sell_2", "emergency_sell"]
    selected = st.selectbox("거래 구분", actions, label_visibility="collapsed")
    filtered = orders if selected == "전체" else [
        item for item in orders if item["action"] == selected
    ]
    rows = [
        {
            "체결 시각": _format_kst(item["completed_at"]),
            "구분": item["action"],
            "매수/매도": "매수" if item["side"] == "buy" else "매도",
            "체결 가격": float(item["average_price"]),
            "체결 수량": float(item["executed_volume"]),
            "총 체결 금액": float(item["executed_funds"]),
            "수수료": float(item["paid_fee"]),
            "주문 UUID": item["uuid"],
            "주문 상태": item["state"],
            "다음 phase": item["next_phase"],
        }
        for item in filtered
    ]
    frame = pd.DataFrame(rows)
    st.download_button(
        "CSV 다운로드",
        data=frame.to_csv(index=False).encode("utf-8-sig"),
        file_name="huntbot-trades.csv",
        mime="text/csv",
        disabled=frame.empty,
    )
    if frame.empty:
        st.info("수집된 자동매매 체결 내역이 없습니다.")
    else:
        st.dataframe(frame, hide_index=True, use_container_width=True)


def _render_charts(st, alt, pd, orders, candles, snapshots, summary) -> None:
    if not candles:
        st.info("가격과 RSI 차트를 표시할 데이터가 없습니다.")
    else:
        price = pd.DataFrame(
            {
                "시각": [item["timestamp"] for item in candles],
                "가격": [float(item["close"]) for item in candles],
                "RSI": [item["rsi"] for item in candles],
            }
        )
        price["시각"] = pd.to_datetime(price["시각"])
        trade_rows = [
            {
                "시각": item["completed_at"],
                "가격": float(item["average_price"]),
                "구분": item["action"],
                "방향": "매수" if item["side"] == "buy" else "매도",
            }
            for item in orders
            if item["completed_at"]
        ]
        trades = pd.DataFrame(trade_rows)
        price_domain = chart_domain(price["가격"].tolist(), padding_ratio=0.08)
        line = alt.Chart(price).mark_line(color="#4361a8").encode(
            x=alt.X("시각:T", title=None),
            y=alt.Y(
                "가격:Q",
                title="KRW",
                scale=alt.Scale(domain=list(price_domain), zero=False),
            ),
        )
        chart = line
        if not trades.empty:
            trades["시각"] = pd.to_datetime(trades["시각"])
            points = alt.Chart(trades).mark_point(size=90, filled=True).encode(
                x="시각:T",
                y="가격:Q",
                color=alt.Color(
                    "방향:N",
                    scale=alt.Scale(
                        domain=["매수", "매도"],
                        range=["#2d7d67", "#b44b4b"],
                    ),
                ),
                shape=alt.Shape("구분:N"),
                tooltip=["시각:T", "구분:N", "가격:Q"],
            )
            chart += points
        st.altair_chart(chart.properties(title="HUNT 가격과 체결 지점", height=340), use_container_width=True)

        rsi_values = [float(value) for value in price["RSI"].dropna().tolist()]
        rsi_domain = chart_domain(
            [*rsi_values, 40, 45, 60, 65],
            padding_ratio=0.08,
            fallback=(35, 70),
        )
        rsi_chart = alt.Chart(price).mark_line(color="#6b5ca5").encode(
            x=alt.X("시각:T", title=None),
            y=alt.Y(
                "RSI:Q",
                scale=alt.Scale(domain=list(rsi_domain), zero=False),
            ),
        )
        thresholds = pd.DataFrame({"기준": [40, 45, 60, 65]})
        rules = alt.Chart(thresholds).mark_rule(strokeDash=[4, 4]).encode(
            y="기준:Q",
            color=alt.value("#9299a8"),
        )
        st.altair_chart((rsi_chart + rules).properties(title="RSI 14", height=260), use_container_width=True)

    curve = pd.DataFrame(summary.realized_curve, columns=["시각", "누적 실현 손익"])
    if not curve.empty:
        curve["시각"] = pd.to_datetime(curve["시각"])
        pnl_domain = chart_domain(
            curve["누적 실현 손익"].astype(float).tolist(),
            padding_ratio=0.12,
        )
        pnl_chart = alt.Chart(curve).mark_line(color="#2d7d67").encode(
            x=alt.X("시각:T", title=None),
            y=alt.Y(
                "누적 실현 손익:Q",
                title="KRW",
                scale=alt.Scale(domain=list(pnl_domain), zero=False),
            ),
            tooltip=["시각:T", "누적 실현 손익:Q"],
        )
        st.altair_chart(
            pnl_chart.properties(title="누적 실현손익", height=260),
            use_container_width=True,
        )
    if snapshots:
        equity = pd.DataFrame(
            {
                "시각": [item["collected_at"] for item in snapshots],
                "계좌 평가금액": [float(item["account_value"]) for item in snapshots],
            }
        )
        equity["시각"] = pd.to_datetime(equity["시각"])
        equity_domain = chart_domain(
            equity["계좌 평가금액"].tolist(),
            padding_ratio=0.08,
        )
        equity_chart = alt.Chart(equity).mark_line(color="#4361a8").encode(
            x=alt.X("시각:T", title=None),
            y=alt.Y(
                "계좌 평가금액:Q",
                title="KRW",
                scale=alt.Scale(domain=list(equity_domain), zero=False),
            ),
            tooltip=["시각:T", "계좌 평가금액:Q"],
        )
        st.altair_chart(
            equity_chart.properties(title="계좌 평가금액", height=260),
            use_container_width=True,
        )
    emergencies = [item for item in orders if item["is_emergency"]]
    if emergencies:
        st.error(
            "Emergency 체결: "
            + ", ".join(_format_kst(item["completed_at"]) for item in emergencies)
        )


def _render_methodology(st, summary) -> None:
    st.markdown(
        """
        ### 손익 용어
        - **실현손익**: 매도를 완료해 이미 확정된 손익입니다.
        - **현재 평가손익**: 아직 보유 중인 HUNT를 현재 최우선 매수호가로
          평가한 미확정 손익입니다.
        - **총손익**: 실현손익과 현재 평가손익의 합입니다.

        ### 계산 기준
        - 주문 UUID를 고유키로 사용하며 Upbit 주문 상세 체결을 우선합니다.
        - `state=cancel`이어도 체결 수량이나 체결 내역이 있으면 거래로 집계합니다.
        - 매수 원가는 체결 금액과 수수료의 합, 매도 대금은 체결 금액에서 수수료를 뺀 값입니다.
        - 실현손익은 수집된 체결을 시간순으로 적용한 이동평균 원가 방식입니다.
        - 현재 평가손익은 `HUNT 잔고 × (최우선 매수호가 - Upbit 평균 매수가)`입니다.
        - 총손익은 확인 가능한 실현손익과 현재 평가손익의 합입니다.
        - 수익률 분모는 수집된 누적 매수 금액입니다.
        - 최대 낙폭은 평가금액 스냅샷이 2개 이상이고 1시간 이상 누적된 경우만 표시합니다.

        ### 한계
        수집 시작 전 보유분, 입출금, 수동 주문, 동기화 범위를 벗어난 주문은 원가를
        완전히 복원하지 못할 수 있습니다. 이 경우 실현손익은 부분 집계로 표시됩니다.
        """
    )


def _apply_style(st) -> None:
    st.markdown(
        """
        <style>
        .block-container { max-width: 1440px; padding-top: 1.6rem; }
        .status-line {
            border-top: 1px solid #d9dee8;
            border-bottom: 1px solid #d9dee8;
            padding: .75rem 0;
            margin-bottom: 1rem;
        }
        .status-ok, .status-warning, .status-danger {
            color: white; border-radius: 3px; padding: .18rem .48rem;
            font-size: .8rem; font-weight: 700;
        }
        .status-ok { background: #2d7d67; }
        .status-warning { background: #a8701c; }
        .status-danger { background: #ad3f45; }
        div[data-testid="stMetric"] {
            border-left: 2px solid #d9dee8;
            padding-left: .75rem;
        }
        div[data-testid="stMetricValue"] { font-size: 1.55rem; }
        @media (max-width: 640px) {
            .block-container { padding: 1rem .75rem 3rem; }
            h1 { font-size: 1.55rem !important; }
            div[data-testid="stMetricValue"] { font-size: 1.1rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _format_kst(value: str | None) -> str:
    if not value:
        return "-"
    timestamp = datetime.fromisoformat(value)
    return timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _format_watch(value: str | None) -> str:
    if not value:
        return "-"
    timestamp = datetime.fromisoformat(value)
    return timestamp.astimezone().strftime("%H:%M:%S")


def _number(snapshot: dict | None, key: str, digits: int) -> str:
    if not snapshot or snapshot.get(key) is None:
        return "-"
    value = snapshot[key]
    return f"{value:,.{digits}f}"


def _hunt_value(snapshot: dict | None) -> str:
    if not snapshot:
        return "-"
    value = snapshot["hunt_balance"] * snapshot["best_bid"]
    return _krw(value)


def _krw(value: Decimal) -> str:
    return f"{value:,.0f} KRW"


def _optional_krw(value: Decimal | None) -> str:
    return f"{value:,.2f} KRW" if value is not None else "-"


if __name__ == "__main__":
    main()
