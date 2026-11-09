"""Persistent display names; stable portfolio IDs preserve holdings and layouts."""
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
import unicodedata

from portfolio_app import portfolio_store

_LOCK = RLock()


def names_path():
    return portfolio_store.PORTFOLIO_PATH.with_name("portfolio_names.json")


def _validate_name(name):
    if not isinstance(name, str) or any(unicodedata.category(c).startswith("C") for c in name):
        raise ValueError("Podaj poprawną nazwę portfela.")
    name = " ".join(name.split())
    if not 1 <= len(name) <= 40:
        raise ValueError("Nazwa portfela musi mieć od 1 do 40 znaków.")
    return name


def _name_key(name):
    return unicodedata.normalize("NFKC", name).casefold()


def load_portfolio_names():
    path = names_path()
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(saved, dict) or any(key not in portfolio_store.PORTFOLIOS for key in saved):
        raise ValueError("Nieprawidłowy plik nazw portfeli.")
    names = {key: _validate_name(saved.get(key, key)) for key in portfolio_store.PORTFOLIOS}
    if len({_name_key(name) for name in names.values()}) != len(names):
        raise ValueError("Nazwy portfeli muszą być różne.")
    return names


def rename_portfolio(portfolio, name, expected_name):
    if portfolio not in portfolio_store.PORTFOLIOS:
        raise ValueError("Podaj poprawną nazwę portfela.")
    name = _validate_name(name)
    with _LOCK:
        names = load_portfolio_names()
        if names[portfolio] != expected_name:
            raise ValueError("Nazwa zmieniła się w innej karcie. Odśwież stronę.")
        if any(key != portfolio and _name_key(value) == _name_key(name) for key, value in names.items()):
            raise ValueError("Nazwy portfeli muszą być różne.")
        names[portfolio] = name
        path = names_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".names-", suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                json.dump(names, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
