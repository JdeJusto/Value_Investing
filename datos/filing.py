from bs4 import BeautifulSoup
import re

class Filing:
    def __init__(self, path):
        self.path = path
        self.raw_content = self._load_file()
        self.text = self._clean_text()

    def _load_file(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return f.read()

    def _clean_text(self):
        # Si es HTML, quitamos tags
        soup = BeautifulSoup(self.raw_content, "lxml")
        return soup.get_text(separator=" ")