import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
from typing import Optional, Dict, Any


# ---------------------------
# Data utilities
# ---------------------------
def _get_price_series(ticker: str, start: str, end: Optional[str]):
    df = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    if isinstance(df, pd.DataFrame) and "Adj Close" in df.columns:
        s = df["Adj Close"]
    elif isinstance(df, pd.DataFrame) and "Close" in df.columns:
        s = df["Close"]
    else:
        raise ValueError(f"Price column not found for {ticker}. Columns={getattr(df, 'columns', None)}")
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    return s


def load_tqqq_fx(start: str, end: Optional[str], seed_ticker="TQQQ", fx_ticker="JPY=X", use_fx=True) -> pd.DataFrame:
    px = _get_price_series(seed_ticker, start, end).rename("PX")
    if use_fx:
        fx = _get_price_series(fx_ticker, start, end).rename("FX")
        df = pd.concat([px, fx], axis=1).dropna()
    else:
        df = px.to_frame()
        df["FX"] = 1.0
    df = df.sort_index()
    return df


# ---------------------------
# Metrics
# ---------------------------
def compute_mdd(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def compute_cagr(equity: pd.Series) -> float:
    days = (equity.index[-1] - equity.index[0]).days
    years = days / 365.25
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0)


def make_buyhold_equity_yen(df: pd.DataFrame, yen_initial: float) -> pd.Series:
    first = df.index[0]
    usd0 = yen_initial / float(df.loc[first, "FX"])
    shares = usd0 / float(df.loc[first, "PX"])
    eq_usd = shares * df["PX"]
    eq_yen = eq_usd * df["FX"]
    return eq_yen.rename("buyhold")


# ---------------------------
# Strategy backtest (two entry modes)
# ---------------------------
def backtest_strategy(
    df: pd.DataFrame,
    yen_initial: float = 500_000,
    take_profit: float = 0.20,
    reenter_dd: float = 0.10,
    fee_rate: float = 0.001,
    entry_mode: str = "dd",         # "dd" or "dd_rebound"
    rebound_from_trough: float = 0.05,  # troughから+5%戻したら買う
    up_days: int = 5,               # 連続上昇日数（=約1週間）
) -> Dict[str, Any]:
    """
    entry_mode:
      - "dd": 直近高値から-10%で即BUY（従来）
      - "dd_rebound": 直近高値から-10%を満たした後、
                      (a) trough（最安値）から+5%戻す AND
                      (b) 直近up_daysが連続上昇
                      の両方を満たしたらBUY（落ちるナイフ回避狙い）
    """
    first_day = df.index[0]
    fx0 = float(df.loc[first_day, "FX"])
    cash_usd = yen_initial / fx0
    shares = 0.0
    entry_px = None
    in_position = False

    # cash state trackers
    wait_peak = float(df.loc[first_day, "PX"])  # 利確後に追う直近高値
    dd_active = False                           # -10%に入ったか
    trough = float(df.loc[first_day, "PX"])     # dd_active中の最安値

    # logs
    equity_yen, actions, in_pos = [], [], []

    px = df["PX"].astype(float)

    # 連続上昇判定用（当日終値が前日終値より高い日がup_days連続）
    up = (px.diff() > 0).astype(int)
    up_streak = up.groupby((up == 0).cumsum()).cumsum()

    for i, (dt, row) in enumerate(df.iterrows()):
        px_t = float(row["PX"])
        fx_t = float(row["FX"])
        action = "HOLD"

        if in_position:
            # take profit
            if px_t >= entry_px * (1.0 + take_profit):
                gross_usd = shares * px_t
                cash_usd = gross_usd * (1.0 - fee_rate)
                shares = 0.0
                in_position = False
                entry_px = None

                # reset cash trackers
                wait_peak = px_t
                dd_active = False
                trough = px_t

                action = "SELL"

        else:
            # update peak while cash
            if px_t > wait_peak:
                wait_peak = px_t

            dd_trigger = px_t <= wait_peak * (1.0 - reenter_dd)

            if entry_mode == "dd":
                if dd_trigger:
                    # BUY immediately
                    net_cash = cash_usd * (1.0 - fee_rate)
                    shares = net_cash / px_t
                    cash_usd = 0.0
                    in_position = True
                    entry_px = px_t
                    dd_active = False
                    trough = px_t
                    action = "BUY"

            elif entry_mode == "dd_rebound":
                # -10%に入ったら監視開始
                if dd_trigger and not dd_active:
                    dd_active = True
                    trough = px_t
                if dd_active:
                    if px_t < trough:
                        trough = px_t

                    # 条件: troughから+5%回復 かつ 直近up_days連続上昇
                    cond_rebound = px_t >= trough * (1.0 + rebound_from_trough)
                    cond_upstreak = int(up_streak.loc[dt]) >= up_days

                    if cond_rebound and cond_upstreak:
                        net_cash = cash_usd * (1.0 - fee_rate)
                        shares = net_cash / px_t
                        cash_usd = 0.0
                        in_position = True
                        entry_px = px_t
                        dd_active = False
                        trough = px_t
                        action = "BUY"
            else:
                raise ValueError("entry_mode must be 'dd' or 'dd_rebound'")

        equity_usd = cash_usd + shares * px_t
        equity_yen.append(equity_usd * fx_t)
        actions.append(action)
        in_pos.append(1 if in_position else 0)

    out = df.copy()
    out["equity_yen"] = equity_yen
    out["action"] = actions
    out["in_position"] = in_pos

    trades = out[out["action"].isin(["BUY", "SELL"])].copy()

    summary = {
        "final_yen": float(out["equity_yen"].iloc[-1]),
        "return_pct": float(out["equity_yen"].iloc[-1] / yen_initial - 1.0) * 100.0,
        "cagr_pct": compute_cagr(out["equity_yen"]) * 100.0,
        "mdd_pct": compute_mdd(out["equity_yen"]) * 100.0,
        "num_buys": int((out["action"] == "BUY").sum()),
        "num_sells": int((out["action"] == "SELL").sum()),
    }
    return {"out": out, "trades": trades, "summary": summary}


# ---------------------------
# Monthly shifting simulation (walk-forward starts)
# ---------------------------
def month_start_dates(df: pd.DataFrame) -> list:
    # 各月の最初の取引日
    g = df.groupby([df.index.year, df.index.month])
    starts = [idxs.index[0] for _, idxs in g]
    return starts


def simulate_monthly_shifted(
    df_all: pd.DataFrame,
    yen_initial: float = 500_000,
    min_years: float = 2.0,  # 短すぎる期間は除外
    take_profit: float = 0.20,
    reenter_dd: float = 0.10,
    fee_rate: float = 0.001,
    entry_mode: str = "dd",
    rebound_from_trough: float = 0.05,
    up_days: int = 5,
) -> pd.DataFrame:
    starts = month_start_dates(df_all)

    rows = []
    for s in starts:
        df = df_all.loc[s:].copy()
        if df.empty:
            continue

        # 期間が短いものは除外（例：最終月付近）
        days = (df.index[-1] - df.index[0]).days
        years = days / 365.25
        if years < min_years:
            continue

        # Strategy
        st = backtest_strategy(
            df,
            yen_initial=yen_initial,
            take_profit=take_profit,
            reenter_dd=reenter_dd,
            fee_rate=fee_rate,
            entry_mode=entry_mode,
            rebound_from_trough=rebound_from_trough,
            up_days=up_days,
        )
        eq_st = st["out"]["equity_yen"]

        # Buy&Hold
        eq_bh = make_buyhold_equity_yen(df, yen_initial)

        rows.append({
            "start_date": str(df.index[0].date()),
            "end_date": str(df.index[-1].date()),
            "years": years,
            "strategy_final_yen": float(eq_st.iloc[-1]),
            "strategy_return_pct": float(eq_st.iloc[-1] / yen_initial - 1.0) * 100.0,
            "strategy_cagr_pct": compute_cagr(eq_st) * 100.0,
            "strategy_mdd_pct": compute_mdd(eq_st) * 100.0,
            "buyhold_final_yen": float(eq_bh.iloc[-1]),
            "buyhold_return_pct": float(eq_bh.iloc[-1] / yen_initial - 1.0) * 100.0,
            "buyhold_cagr_pct": compute_cagr(eq_bh) * 100.0,
            "buyhold_mdd_pct": compute_mdd(eq_bh) * 100.0,
            "delta_return_pctpt": (float(eq_st.iloc[-1] / yen_initial - 1.0) - float(eq_bh.iloc[-1] / yen_initial - 1.0)) * 100.0,
        })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    # 期間は広めに取る（開始日をずらすので）
    df_all = load_tqqq_fx(start="2016-01-01", end=None, use_fx=True)

    # 1) 従来：-10%で即BUY
    res_dd = simulate_monthly_shifted(
        df_all,
        yen_initial=500_000,
        min_years=2.0,
        take_profit=0.20,
        reenter_dd=0.10,
        fee_rate=0.001,
        entry_mode="dd",
    )

    # 2) 改良案：-10%到達後、troughから+5%戻し & 5日連続上昇でBUY
    res_reb = simulate_monthly_shifted(
        df_all,
        yen_initial=500_000,
        min_years=2.0,
        take_profit=0.20,
        reenter_dd=0.10,
        fee_rate=0.001,
        entry_mode="dd_rebound",
        rebound_from_trough=0.05,
        up_days=5,
    )

    # 集計表示
    def summarize(df: pd.DataFrame, name: str):
        if df.empty:
            print(f"{name}: no results")
            return
        win_rate = (df["delta_return_pctpt"] > 0).mean() * 100.0
        print(f"\n== {name} ==")
        print(f"windows: {len(df)}")
        print(f"win_rate_vs_buyhold: {win_rate:.1f}%")
        print(f"median_delta_return_pctpt: {df['delta_return_pctpt'].median():.2f}")
        print(f"median_strategy_mdd_pct: {df['strategy_mdd_pct'].median():.2f}")
        print(f"median_buyhold_mdd_pct: {df['buyhold_mdd_pct'].median():.2f}")

    summarize(res_dd, "ENTRY=DD (buy on -10%)")
    summarize(res_reb, "ENTRY=DD+REBOUND (avoid catching knife)")

    # 結果をCSV保存（必要なら）
    res_dd.to_csv("walkforward_dd.csv", index=False)
    res_reb.to_csv("walkforward_dd_rebound.csv", index=False)
    print("\nSaved: walkforward_dd.csv, walkforward_dd_rebound.csv")

    # ざっくり可視化：開始日ごとの超過リターン
    plt.figure()
    plt.plot(pd.to_datetime(res_dd["start_date"]), res_dd["delta_return_pctpt"], label="dd")
    plt.plot(pd.to_datetime(res_reb["start_date"]), res_reb["delta_return_pctpt"], label="dd_rebound")
    plt.axhline(0, linestyle="--")
    plt.xlabel("Start date")
    plt.ylabel("Strategy - Buy&Hold (return pct-pt)")
    plt.title("Walk-forward (monthly starts): excess return vs buy&hold")
    plt.legend()
    plt.tight_layout()
    plt.show()
