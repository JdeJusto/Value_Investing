def get_tickers():
    mode = input("?Varios tickers? (y/n): ").strip().lower()

    if mode == "y":
        raw = input("Introduce tickers separados por comas: ")
        tickers = [t.strip().upper() for t in raw.split(",")]
    else:
        tickers = [input("Introduce ticker: ").strip().upper()]

    return tickers
