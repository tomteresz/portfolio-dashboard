"""Validated portfolio positions, persisted atomically beside the application."""

import json
import math
import os
from pathlib import Path
import re
import tempfile
from threading import RLock

PORTFOLIOS = ("Erste-DM", "XTB")
SHARE_DECIMALS = {"Erste-DM": 0, "XTB": 4}
PORTFOLIO_PATH = Path(os.environ.get("PORTFOLIO_PATH", str(Path(__file__).resolve().parent.parent / "data" / "portfolio.json")))
_LOCK = RLock()


def validate_position(position, *, enforce_whole_shares=False):
    symbol = str(position.get("symbol", "")).strip().upper()
    name = str(position.get("name", "")).strip() or symbol
    portfolio = position.get("portfolio")
    if portfolio == "Długoterminowy":
        portfolio = "Erste-DM"
    if portfolio not in PORTFOLIOS:
        raise ValueError("Wybierz portfel Erste-DM lub XTB.")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,24}", symbol):
        raise ValueError("Podaj poprawny symbol Yahoo Finance, np. AAPL lub BRK-B.")
    if len(name) > 80:
        raise ValueError("Nazwa spółki może mieć najwyżej 80 znaków.")
    numbers = {}
    for key, label in (("shares", "Liczba akcji"), ("average_price", "Średnia cena zakupu")):
        try:
            value = float(position.get(key, 0))
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"{label} musi być dodatnią liczbą.") from None
        if isinstance(position.get(key), bool) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{label} musi być dodatnią, skończoną liczbą.")
        numbers[key] = value
    if enforce_whole_shares and SHARE_DECIMALS[portfolio] == 0 and not numbers["shares"].is_integer():
        raise ValueError("Podaj liczbę akcji w pełnych sztukach.")
    cost = numbers["shares"] * numbers["average_price"]
    if not math.isfinite(cost) or cost <= 0:
        raise ValueError("Wartość pozycji musi być dodatnią, skończoną liczbą.")
    return {"portfolio": portfolio, "name": name, "symbol": symbol, **numbers}


def load_positions(path=None):
    path = Path(path) if path is not None else PORTFOLIO_PATH
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    if not isinstance(records, list):
        raise ValueError("Plik portfolio.json musi zawierać listę pozycji.")
    result, seen = [], set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Każda pozycja musi być obiektem JSON.")
        record = validate_position(record)
        key = (record["portfolio"], record["symbol"])
        if key in seen:
            raise ValueError(f"Powtórzony symbol {key[1]} w portfelu {key[0]}.")
        seen.add(key)
        result.append(record)
    return result


def update_position(original, replacement, path=None):
    replacement = validate_position(replacement, enforce_whole_shares=True)
    path = Path(path) if path is not None else PORTFOLIO_PATH
    with _LOCK:
        records = load_positions(path)
        matches = [i for i, r in enumerate(records)
                   if (r["portfolio"], r["symbol"]) == (original["portfolio"], original["symbol"])]
        if not matches or records[matches[0]] != original:
            raise ValueError("Pozycja zmieniła się od otwarcia formularza. Odśwież stronę i spróbuj ponownie.")
        index = matches[0]
        if any(i != index and (r["portfolio"], r["symbol"]) ==
               (replacement["portfolio"], replacement["symbol"]) for i, r in enumerate(records)):
            raise ValueError("Ten symbol już istnieje w docelowym portfelu. Nie można połączyć pozycji automatycznie.")
        records[index] = replacement
        _write_positions(records, path)


def add_position(position, path=None):
    """Add a first purchase or merge it into the current weighted average."""
    purchase = validate_position(position, enforce_whole_shares=True)
    path = Path(path) if path is not None else PORTFOLIO_PATH
    with _LOCK:
        records = load_positions(path)
        for index, current in enumerate(records):
            if (current["portfolio"], current["symbol"]) != (purchase["portfolio"], purchase["symbol"]):
                continue
            try:
                shares = current["shares"] + purchase["shares"]
                cost = math.fsum((current["shares"] * current["average_price"],
                                  purchase["shares"] * purchase["average_price"]))
                result = validate_position({**current, "shares": shares, "average_price": cost / shares})
            except (OverflowError, ZeroDivisionError):
                raise ValueError("Wartość pozycji musi być dodatnią, skończoną liczbą.") from None
            records[index] = result
            break
        else:
            result = purchase
            records.append(result)
        _write_positions(records, path)
    return result


def remove_position(original, path=None):
    """Remove the selected aggregate holding only if it has not changed."""
    path = Path(path) if path is not None else PORTFOLIO_PATH
    with _LOCK:
        records = load_positions(path)
        index = next((i for i, record in enumerate(records)
                      if (record["portfolio"], record["symbol"]) == (original["portfolio"], original["symbol"])), None)
        if index is None or records[index] != original:
            raise ValueError("Pozycja zmieniła się od otwarcia formularza. Odśwież stronę i spróbuj ponownie.")
        del records[index]
        _write_positions(records, path)


def _write_positions(records, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".portfolio-", suffix=".tmp", delete=False) as temp:
            temp_path = Path(temp.name)
            json.dump(records, temp, ensure_ascii=False, indent=2, allow_nan=False)
            temp.write("\n")
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
