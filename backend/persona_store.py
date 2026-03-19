"""In-memory persona store backed by pandas DataFrame.

Replaces SQLite for persona queries. Loaded once at startup from parquet.
All filter/sample/lookup operations are sub-millisecond on 1M rows.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import pandas as pd

from config import settings

if TYPE_CHECKING:
    from models import FinancialExtension

logger = logging.getLogger(__name__)

# Singleton instance — set by init_persona_store()
_store: Optional["PersonaStore"] = None


class PersonaStore:
    """In-memory persona data with filter, sample, and lookup operations."""

    def __init__(self, df: pd.DataFrame):
        # Fill NaN with None for JSON serialization
        self._df = df.where(df.notna(), None)
        self._financial_cache: dict[str, dict] = {}  # uuid → serialized FinancialExtension
        logger.info("PersonaStore initialized with %d rows", len(df))

    def total_count(self) -> int:
        return len(self._df)

    def get_filters(self) -> dict:
        df = self._df
        sex_vals = sorted(df["sex"].dropna().unique().tolist())
        regions = sorted(df["region"].dropna().unique().tolist())
        prefectures = sorted(df["prefecture"].dropna().unique().tolist())
        education_levels = sorted(df["education_level"].dropna().unique().tolist())
        occ_counts = (
            df["occupation"].dropna()
            .value_counts()
            .head(50)
            .index.tolist()
        )
        return {
            "sex": sex_vals,
            "age_ranges": ["20-29", "30-39", "40-49", "50-59", "60-69", "70+"],
            "regions": regions,
            "prefectures": prefectures,
            "occupations_top50": occ_counts,
            "education_levels": education_levels,
            "total_count": len(df),
        }

    def _apply_filters(
        self,
        sex: Optional[str] = None,
        age_min: Optional[int] = None,
        age_max: Optional[int] = None,
        region: Optional[str] = None,
        prefecture: Optional[str] = None,
        occupation: Optional[str] = None,
        education: Optional[str] = None,
    ) -> pd.DataFrame:
        df = self._df
        if sex:
            df = df[df["sex"] == sex]
        if age_min is not None:
            df = df[df["age"] >= age_min]
        if age_max is not None:
            df = df[df["age"] <= age_max]
        if region:
            df = df[df["region"] == region]
        if prefecture:
            df = df[df["prefecture"] == prefecture]
        if occupation:
            df = df[df["occupation"].str.contains(occupation, na=False)]
        if education:
            df = df[df["education_level"].str.contains(education, na=False)]
        return df

    def count(self, **filters) -> int:
        return len(self._apply_filters(**filters))

    def sample(self, count: int = 8, **filters) -> tuple[int, list[dict]]:
        filtered = self._apply_filters(**filters)
        total = len(filtered)
        if total == 0:
            return 0, []
        n = min(count, total)
        sampled = filtered.sample(n=n)
        rows = sampled.to_dict(orient="records")
        return total, rows

    def get_cached_financial(self, uuid: str) -> dict | None:
        return self._financial_cache.get(uuid)

    def set_cached_financial(self, uuid: str, ext: "FinancialExtension") -> None:
        self._financial_cache[uuid] = ext.model_dump(exclude_none=False)

    def get_persona(self, uuid: str) -> Optional[dict]:
        matches = self._df[self._df["uuid"] == uuid]
        if matches.empty:
            return None
        return matches.iloc[0].to_dict()


def init_persona_store() -> "PersonaStore":
    """Load parquet into memory. Downloads from HuggingFace if needed."""
    from db import extract_name, _download_dataset

    raw_parquet = (settings.persona_parquet_path or "").strip()
    if raw_parquet:
        parquet_path = Path(raw_parquet).expanduser()
    else:
        parquet_path = Path(settings.data_dir) / "personas.parquet"

    if not parquet_path.exists():
        logger.info("Parquet not found — downloading from HuggingFace...")
        _download_dataset(parquet_path)

    logger.info("Loading parquet into memory: %s", parquet_path)
    df = pd.read_parquet(str(parquet_path))

    # Extract names if not present
    if "name" not in df.columns:
        df["name"] = df["persona"].apply(extract_name)

    logger.info("Loaded %d personas into memory", len(df))

    global _store
    _store = PersonaStore(df)
    return _store


def get_store() -> "PersonaStore":
    """Get the singleton PersonaStore. Raises if not initialized."""
    if _store is None:
        raise RuntimeError("PersonaStore not initialized — call init_persona_store() first")
    return _store
