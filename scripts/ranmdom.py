import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

def simulate_etf_lump_sum_yen(
    tickers=("TQQQ", "JEPQ"),
    yen_amount=500_000,
    start="2015-04-01",
    end=None,  # Noneで最新まで
    fx_ticker="JPY=X",  # USDJPY（1 USD = 何JPY）
):
    """
    前提: 米国ETFをUSD建てで購入（円→ドルに両替）し、評価額を円換算して推移を出す。
    - Adj Close を使って「分配金・分割調整込み」の推移を近似（JEPQの再投資もここに反映される想定）
    - 円換算: 当日のUSD評価額 × 当日のUSDJPY
    """
    px = yf.download(list(tickers), start=start, end=end, auto_adjust=False, progress=False)["Adj Close"]
    fx = yf.download(fx_ticker, start=start, end=end, auto_adjust=False, progress=False)["Adj Close"]
    

    
    # 整形（単一列になるケース対策）
    if isinstance(px, pd.Series):
        px = px.to_frame()
    if isinstance(fx, pd.DataFrame):
        fx = fx.iloc[:, 0]
    
    fx = fx.rename("USDJPY")

    df = px.join(fx, how="inner").dropna()
    first_day = df.index[0]
    last_day = df.index[-1]

    usd_amount = yen_amount / df.loc[first_day, "USDJPY"]  # 初日に円→ドル換算
    out = {}

    for t in tickers:
        shares = usd_amount / df.loc[first_day, t]
        usd_value = shares * df[t]
        yen_value = usd_value * df["USDJPY"]
        out[t] = yen_value.rename(t)

    values = pd.concat(out.values(), axis=1)

    summary = []
    for t in tickers:
        summary.append({
            "ticker": t,
            "start_date": str(first_day.date()),
            "end_date": str(last_day.date()),
            "start_value_yen": float(values[t].iloc[0]),
            "end_value_yen": float(values[t].iloc[-1]),
            "multiple": float(values[t].iloc[-1] / values[t].iloc[0]),
            "return_pct": float(values[t].iloc[-1] / values[t].iloc[0] - 1.0) * 100.0,
        })
    summary_df = pd.DataFrame(summary)

    # プロット
    plt.figure()
    for t in tickers:
        plt.plot(values.index, values[t], label=t)
    plt.xlabel("Date")
    plt.ylabel("Portfolio value (JPY)")
    plt.title(f"Lump-sum {yen_amount:,} JPY from {start} (Adj Close approx, FX included)")
    plt.legend()
    plt.tight_layout()
    plt.show()

    return summary_df, values

if __name__ == "__main__":
    summary_df, values = simulate_etf_lump_sum_yen(
        tickers=("TQQQ", "JEPQ","SPXL"),
        yen_amount=500_000,     # N円に変更
        start="2015-04-01",
    )
    print(summary_df.to_string(index=False))
