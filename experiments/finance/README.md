# Finance Experiments

`experiments/finance/` は STRING アプリ本体とは無関係な検証用スクリプト置き場です。

## 追加依存
本ディレクトリのスクリプト実行には、ルートの `requirements.txt` とは別に以下が必要です。

- `yfinance`
- `numpy`
- `matplotlib`
- `pandas`

## 実行例
```powershell
pip install -r experiments/finance/requirements.txt
python experiments/finance/backtest_tqqq_strategy.py
python experiments/finance/simulate_etf_lump_sum_yen.py
```
