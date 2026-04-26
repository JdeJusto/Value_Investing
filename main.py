from edgar import set_identity, Company
import yfinance as yf
import pandas as pd
import consola
from analyzer import StockAnalyzer

set_identity("Jaime jaimedejusto@gmail.com")

# ─────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────
def main():
    tickers = consola.get_tickers()

    results = []

    print("\nAnalizando...\n")

    for t in tickers:
        print(f"→ {t}")

        analyzer = StockAnalyzer(t)
        result = analyzer.analyze()

        if result:
            results.append(result)
            print(f"  Score: {result['score']:.4f}")
        else:
            print("  Sin datos suficientes")

    if not results:
        print("\nNo data extracted")
        return

    df = pd.DataFrame(results).sort_values("score", ascending=False)

    print("\n════════ RESULTADOS ════════\n")
    print(df)

    print("\n🏆 Top pick:", df.iloc[0]["ticker"])


if __name__ == "__main__":
    main()