"""Streaming repetition detector for LLM output."""
from collections import Counter


class RepetitionDetector:
    """Detects repetitive n-gram loops in streaming text.

    Feed chunks as they arrive; returns True when repetition is detected.
    """

    def __init__(self, ngram_size: int = 8, threshold: int = 4, window_chars: int = 300):
        self.ngram_size = ngram_size
        self.threshold = threshold
        self.window_chars = window_chars
        self._buffer = ""

    def feed(self, chunk: str) -> bool:
        """Append chunk to buffer and check for repetition.

        Returns True if any n-gram appears >= threshold times in the window.
        """
        self._buffer += chunk
        # Keep only trailing window_chars
        if len(self._buffer) > self.window_chars:
            self._buffer = self._buffer[-self.window_chars:]

        # Need at least enough chars to form one n-gram
        if len(self._buffer) < self.ngram_size:
            return False

        counts = Counter(
            self._buffer[i: i + self.ngram_size]
            for i in range(len(self._buffer) - self.ngram_size + 1)
        )
        return any(c >= self.threshold for c in counts.values())

    def reset(self) -> None:
        """Clear internal buffer."""
        self._buffer = ""
