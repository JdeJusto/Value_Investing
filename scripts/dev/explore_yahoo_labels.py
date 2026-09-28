"""Print the financial statement labels returned by Yahoo Finance for AAPL."""


def main() -> None:
    import yfinance as yf

    ticker = yf.Ticker("AAPL")
    print("\n=== Income statement labels ===")
    for label in ticker.income_stmt.index:
        print(label)

    print("\n=== Balance sheet labels ===")
    for label in ticker.balance_sheet.index:
        print(label)

    print("\n=== Cash flow labels ===")
    for label in ticker.cashflow.index:
        print(label)


if __name__ == "__main__":
    main()
