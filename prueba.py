import yfinance as yf
aapl = yf.Ticker("AAPL")

print("\n=== Income Statement - TODOS los índices ===")
for idx in aapl.income_stmt.index:
    print(idx)

print("\n=== Balance Sheet - TODOS los índices ===")
for idx in aapl.balance_sheet.index:
    print(idx)

print("\n=== Cashflow - TODOS los índices ===")
for idx in aapl.cashflow.index:
    print(idx)