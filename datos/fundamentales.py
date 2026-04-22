class FinancialAnalyzer:
    def __init__(self, filing: Filing):
        self.filing = filing
        self.text = filing.text

    def extract_metrics(self):
        patterns = {
            "revenue": r"(?i)total revenue|net sales",
            "net_income": r"(?i)net income",
        }

        results = {}

        for key, pattern in patterns.items():
            match = re.findall(pattern + r".{0,60}", self.text)
            results[key] = match

        return results

    def run(self):
        metrics = self.extract_metrics()

        return {
            "file": self.filing.path,
            "metrics": metrics
        }
    
    