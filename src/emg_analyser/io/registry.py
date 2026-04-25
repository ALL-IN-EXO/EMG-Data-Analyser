from __future__ import annotations
from pathlib import Path

from .myo_csv import MyoMetricsAdapter
from .camargo_adapter import CamargoAdapter
from .base import DatasetAdapter, TrialHandle

_ADAPTERS: dict[str, DatasetAdapter] = {}


def register(adapter: DatasetAdapter) -> None:
    _ADAPTERS[adapter.name] = adapter


def get_adapter(name: str) -> DatasetAdapter | None:
    return _ADAPTERS.get(name)


def all_adapters() -> list[DatasetAdapter]:
    return list(_ADAPTERS.values())


def detect_adapter(root: Path) -> DatasetAdapter | None:
    """Return the first adapter that finds at least one trial in root."""
    for adapter in _ADAPTERS.values():
        try:
            if adapter.scan(root):
                return adapter
        except Exception:
            continue
    return None


# Register built-in adapters on import
register(MyoMetricsAdapter())
register(CamargoAdapter())
