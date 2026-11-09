"""Persistent table columns, shared across devices using this installation."""
import json
import os
from pathlib import Path
import tempfile
from threading import RLock

import portfolio_app.portfolio_store as portfolio_store

COLUMNS = ["Spółka", "Ticker", "Cena", "Zmiana dzienna %", "Zmiana dzienna USD", "Akcje", "Średnia",
           "Wartość", "Zwrot USD", "Zwrot %", "Udział %",
           "Pre-market", "Pre-market %", "After-hours", "After-hours %"]
LABELS = {"Ticker": "Symbol", "Cena": "Kurs", "Średnia": "Średnia cena zakupu",
          "Zmiana dzienna %": "Zmiana dzienna (%)", "Zmiana dzienna USD": "Zmiana dzienna (USD)",
          "Zwrot USD": "Wynik od zakupu (USD)"}
_LOCK = RLock()


def layout_path():
    return Path(os.environ.get("LAYOUT_PATH", str(portfolio_store.PORTFOLIO_PATH.with_name("layout.json"))))


def _load(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "Długoterminowy" in data:
        data.setdefault("Erste-DM", data.pop("Długoterminowy"))
    if not isinstance(data, dict) or any(
        not isinstance(cols, list)
        or any(not isinstance(c, str) or c not in COLUMNS for c in cols)
        or len(cols) != len(set(cols))
        for cols in data.values()
    ):
        raise ValueError("Nieprawidłowy plik układu kolumn.")
    return data


def columns_for(portfolio):
    return list(_load(layout_path()).get(portfolio, COLUMNS))


def reorder_columns(portfolio, order, base):
    """Persist a drag only if it reorders the current visible columns."""
    if (not isinstance(order, list) or not isinstance(base, list)
            or any(not isinstance(c, str) or c not in COLUMNS for c in order + base)
            or len(order) != len(set(order)) or len(base) != len(set(base))
            or set(order) != set(base)):
        raise ValueError("Nieprawidłowy wybór kolumn.")
    with _LOCK:
        if columns_for(portfolio) != base:
            raise ValueError("Układ zmienił się w innej karcie. Spróbuj ponownie.")
        save_columns(portfolio, order)


def save_columns(portfolio, columns):
    if portfolio not in portfolio_store.PORTFOLIOS or not isinstance(columns, list) or any(c not in COLUMNS for c in columns):
        raise ValueError("Nieprawidłowy wybór kolumn.")
    path = layout_path()
    with _LOCK:
        layouts = _load(path)
        layouts[portfolio] = list(dict.fromkeys(columns))
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".layout-", suffix=".tmp", delete=False) as temp:
                temp_path = Path(temp.name)
                json.dump(layouts, temp, ensure_ascii=False, indent=2)
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
