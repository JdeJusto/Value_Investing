# main.py - con manejo de excepciones por ticker

from edgar import set_identity
import pandas as pd
import consola
import os
from analyzer import StockAnalyzer

set_identity("Jaime jaimedejusto@gmail.com")

# ... (el resto de funciones de interpretación se mantienen igual) ...

def main():
    tickers = consola.get_tickers()
    results = []

    print("\n🔍 Analizando...\n")

    for t in tickers:
        print(f"→ {t}")
        try:
            analyzer = StockAnalyzer(t)
            result = analyzer.analyze()
            if result:
                results.append(result)
                print_analysis(result)   # tu función print_analysis definida antes
            else:
                print(f"  ❌ Sin datos suficientes para {t}")
        except Exception as e:
            print(f"  ❌ Error analizando {t}: {e}")
            continue

    if not results:
        print("\n⚠️ No se pudo extraer datos para ningún ticker.")
        return

    df = pd.DataFrame(results).sort_values("score", ascending=False)
    os.makedirs("outputs", exist_ok=True)
    csv_filename = "outputs/analisis_completo.csv"
    df.to_csv(csv_filename, index=False)
    print(f"\n💾 Resultados guardados en {csv_filename}")

    print("\n" + "═"*80)
    print("🏆 RANKING FINAL (por score)")
    print("═"*80)
    for i, row in df.iterrows():
        ticker = row["ticker"]
        score = row["score"]
        print(f"{i+1}. {ticker} : {score:.4f}" if score is not None else f"{i+1}. {ticker} : sin score")

    print(f"\n🥇 Top pick: {df.iloc[0]['ticker']}")

if __name__ == "__main__":
    main()