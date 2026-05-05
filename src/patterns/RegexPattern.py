import re
from difflib import SequenceMatcher


class RegexPattern:
    def __init__(self, pattern: str, threshold: float = 1.0):
        self.pattern = pattern
        self.regex = re.compile(pattern, re.IGNORECASE)
        self.threshold = threshold

    def match(self, text: str) -> bool:
        if self.threshold == 1.0:
            return bool(self.regex.fullmatch(text))

        matches = self.regex.findall(text)
        if not matches:
            return False

        best_match = max(matches, key=lambda x: len(x)) if isinstance(matches, list) else matches
        similarity = SequenceMatcher(None, best_match, text).ratio()
        return similarity >= self.threshold
