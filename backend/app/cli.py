import os

from dotenv import load_dotenv
import pandas as pd

from backend.analytics.interpretation import print_analysis
from backend.analytics.service import CompanyAnalysisService
from backend.config.settings import get_output_dir
from backend.providers.yahoo import YahooFinanceProvider
from backend.providers.edgar import EdgarProvider
from backend.utils.input import get_tickers

load_dotenv()

sec_email = os.getenv("SEC_EMAIL", "jaimedejusto@gmail.com")
sec_name = os.getenv("SEC_NAME", "Jaime")


def build_service() -> CompanyAnalysisService:
    yahoo = YahooFinanceProvider()
    edgar = EdgarProvider(email=sec_email, name=sec_name)
    return CompanyAnalysisService(
        financial_providers=[yahoo, edgar],
        market_provider=yahoo,
    )


def main():
    service = build_service()
    tickers = get_tickers()
    results = []

    print("\nAnalizando...\n")

    for t in tickers:
        print(f"-> {t}")
        try:
            result = service.analyze(t)
            if result:
                results.append(result)
                print_analysis(result)
            else:
                print(f"  Sin datos suficientes para {t}")
        except Exception as e:
            print(f"  Error analizando {t}: {e}")
            continue

    if not results:
        print("\nNo se pudo extraer datos para ningun ticker.")
        return

    df = pd.DataFrame(results).sort_values("score", ascending=False)
    output_dir = get_output_dir()
    os.makedirs(output_dir, exist_ok=True)
    csv_filename = os.path.join(output_dir, "analisis_completo.csv")
    df.to_csv(csv_filename, index=False)
    print(f"\nResultados guardados en {csv_filename}")

    print("\n" + "="*80)
    print("RANKING FINAL (por score)")
    print("="*80)
    for i, row in df.iterrows():
        ticker = row["ticker"]
        score = row["score"]
        if score is not None:
            print(f"{i+1}. {ticker} : {score:.4f}")
        else:
            print(f"{i+1}. {ticker} : sin score")

    print(f"\nTop pick: {df.iloc[0]['ticker']}")


if __name__ == "__main__":
    main()
