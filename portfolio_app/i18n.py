"""UI language selection. Portfolio keys remain unchanged in saved data."""
import streamlit as st
from contextlib import nullcontext
from functools import lru_cache

EN = {
    "Nazwy portfeli": "Portfolio names",
    "Nowa nazwa portfela": "New portfolio name",
    "Zapisz nazwę": "Save name",
    "Zapisano nazwę portfela.": "Portfolio name saved.",
    "Podaj poprawną nazwę portfela.": "Enter a valid portfolio name.",
    "Nazwa portfela musi mieć od 1 do 40 znaków.": "Portfolio names must contain 1 to 40 characters.",
    "Nieprawidłowy plik nazw portfeli.": "Invalid portfolio names file.",
    "Nazwy portfeli muszą być różne.": "Portfolio names must be different.",
    "Nazwa zmieniła się w innej karcie. Odśwież stronę.": "The name changed in another tab. Refresh the page.",
    "Mapa sektorów S&P 500": "S&P 500 sector map",
    "Kalendarz makro USA · najbliższe 45 dni": "US economic calendar · next 45 days",
    "Niepełny kalendarz makro — niedostępne źródła: ": "Incomplete economic calendar — unavailable sources: ",
    "Brak dostępnych nadchodzących wydarzeń makro.": "No upcoming economic events available.",
    "godzina niepotwierdzona": "time not confirmed",
    "FOMC · decyzja w sprawie stóp": "FOMC · interest rate decision",
    "Technologia": "Technology", "Finanse": "Financials", "Energia": "Energy",
    "Ochrona zdrowia": "Health care", "Przemysł": "Industrials", "Materiały": "Materials",
    "Dobra uznaniowe": "Consumer discretionary", "Dobra podstawowe": "Consumer staples",
    "Użyteczność publiczna": "Utilities", "Nieruchomości": "Real estate", "Usługi komunikacyjne": "Communication services",
    "Mapa sektorów: zmiany dzienne ETF-ów Select Sector SPDR względem poprzedniego zamknięcia, nie wagi kapitalizacji sektorów. Źródło: Yahoo Finance. Dane mogą być opóźnione.": "Sector map: daily Select Sector SPDR ETF changes from the previous close; tiles are not weighted by sector capitalization. Source: Yahoo Finance. Data may be delayed.",
    "Kalendarz makro: Fed, BEA i BLS; przy braku BLS pomocniczo Forex Factory (bieżący tydzień). Brak potwierdzonej godziny nie jest zastępowany szacunkiem. Terminy mogą się zmienić.": "Economic calendar: Fed, BEA and BLS; Forex Factory (current week) supplements unavailable BLS data. Unconfirmed times are not estimated. Dates may change.",
    "Rynek · rosnące / spadające": "Market · advancing / declining",
    "bilans": "net",
    "pb": "bp",
    "Dane chwilowo niedostępne.": "Data temporarily unavailable.",
    "Rentowność obligacji skarbowych USA 10Y. Zmiana w punktach bazowych względem poprzedniego odczytu dziennego.": "US 10-year Treasury yield. Change in basis points from the previous daily observation.",
    "Rosnące / spadające walory na NYSE, Nasdaq i AMEX. Zmiana poniżej to bilans: rosnące minus spadające, nie zmiana względem wczoraj. Finviz nie podaje czasu samego odczytu; dane mogą być opóźnione.": "Advancing / declining issues on NYSE, Nasdaq and AMEX. The delta is net advances, not a day-over-day change. Finviz does not provide an observation timestamp; data may be delayed.",
    "Rosnące / spadające · ostatnie 14 dni": "Advancing / declining · last 14 days",
    "Bilans rynku": "Net advances",
    "Rosnące walory": "Advancing issues",
    "Spadające walory": "Declining issues",
    "Historia pojawi się po pierwszym odczycie zapisanym w ostatnich 30 minutach sesji USA.": "History will appear after the first reading saved during the final 30 minutes of a US session.",
    "Historia szerokości rynku jest chwilowo niedostępna.": "Market breadth history is temporarily unavailable.",
    "Dzienny stosunek wolumenu opcji put do call na akcje. Equity Put/Call Ratio, bez opcji indeksowych i ETF. Wartość bez zmiany dziennej.": "Daily equity option put/call volume ratio, excluding index and ETF options. Level only, without a daily change.",
    "VIX · indeks strachu": "VIX · fear index",
    "ostatnie 14 dni": "last 14 days",
    "Brak danych z ostatnich 14 dni.": "No data for the last 14 days.",
    "WTI (USD za baryłkę)": "WTI (USD per barrel)",
    "Data sesji": "Trading date",
    "Indeks VIX jest chwilowo niedostępny.": "VIX is temporarily unavailable.",
    "Kurs ropy WTI jest chwilowo niedostępny.": "WTI crude oil is temporarily unavailable.",
    "Kontrakty na ropę WTI w USD za baryłkę. Zmiana względem poprzedniego zamknięcia. Dane mogą być opóźnione.": "WTI crude oil futures in USD per barrel. Change from the previous close. Quotes may be delayed.",
    "Indeks zmienności Cboe VIX. Zmiana względem poprzedniego zamknięcia. Wzrost oznacza większą oczekiwaną zmienność.": "Cboe VIX volatility index. Change from the previous close. A rise means higher expected volatility.",
    "pkt": "pts",
    "Nie potwierdzono waluty USD dla notowania.": "Could not confirm USD currency for the quote.",
    "1 USD w PLN. Zmiana względem poprzedniego zamknięcia rynku walutowego.": "1 USD in PLN. Change versus the previous FX session close.",
    "Kurs USD/PLN jest chwilowo niedostępny.": "USD/PLN is temporarily unavailable.",
    "Zainwestowany kapitał w USD przeliczony po bieżącym kursie z pola USD/PLN.": "Invested capital in USD converted at the current rate shown in USD/PLN.",
    "Wartość w USD przeliczona po bieżącym kursie z pola USD/PLN.": "USD value converted at the current rate shown in USD/PLN.",
    "Kalendarz wyników i dywidend — wszystkie portfele": "Earnings and dividend calendar — all portfolios",
    "Pobieranie kalendarza…": "Fetching calendar…",
    "Wyniki finansowe": "Earnings",
    "Dywidenda / akcję brutto": "Gross dividend / share", "Dzień wypłaty": "Payment date",
    "Łącznie brutto (szacunek)": "Gross total (estimate)", "akcji": "shares",
    "Brak zapowiedzianych wydarzeń dla spółek z tego portfela.": "No upcoming events published for this portfolio's companies.",
    "Brak opublikowanych przyszłych dat: ": "No future dates published: ",
    "Niepełne dane kalendarza: ": "Incomplete calendar data: ",
    "Pobierane raz przy otwarciu aplikacji": "Fetched once when the app is opened",
    "Dywidenda na akcję i suma są kwotami brutto. Suma to szacunek dla obecnej liczby akcji, nie potwierdzenie prawa do wypłaty. Ex-dividend to data odcięcia prawa do dywidendy. Terminy wyników mogą być szacunkowe. — oznacza brak danych.":
        "Per-share dividends and totals are gross amounts. The total is an estimate based on current shares, not confirmation of entitlement. Ex-dividend is the entitlement cutoff date. Earnings dates may be estimates. — means unavailable data.",
    "Usuń tę pozycję": "Delete this holding", "Usuń z portfela": "Remove from portfolio",
    "Usunięta zostanie cała pozycja: ": "The entire holding will be removed: ",
    "Usunięto pozycję: ": "Holding removed: ",
    "Portfele są puste. Dodaj pierwszą pozycję przyciskiem u góry.": "Portfolios are empty. Add your first holding using the button above.",
    "Dodaj pozycję": "Add holding", "Portfel": "Portfolio", "Symbol Yahoo Finance": "Yahoo Finance symbol",
    "Liczba kupionych akcji": "Shares purchased", "Cena zakupu jednej akcji (USD)": "Purchase price per share (USD)",
    "Dodaj zakup": "Add purchase", "Dodano zakup: ": "Purchase added: ",
    "Nowy symbol tworzy pozycję. Dla istniejącego dopisujemy akcje i przeliczamy średnią ważoną.":
        "A new symbol creates a holding. For an existing symbol we add the shares and recalculate the weighted average.",
    "Nie udało się zweryfikować symbolu w Yahoo Finance. Spróbuj ponownie.": "Could not verify the symbol with Yahoo Finance. Please try again.",
    "Nie znaleziono akcji lub ETF dla podanego symbolu.": "No stock or ETF found for this symbol.",
    "Aplikacja obsługuje pozycje notowane w USD.": "The app supports holdings quoted in USD.",
    "Brak dostępnej ceny dla podanego symbolu.": "No price is available for this symbol.",
    "Nastroje rynku USA": "US market sentiment",
    "0 = skrajny strach, 100 = skrajna chciwość.": "0 = extreme fear, 100 = extreme greed.",
    "Skrajny strach": "Extreme fear", "Strach": "Fear", "Neutralny": "Neutral",
    "Chciwość": "Greed", "Skrajna chciwość": "Extreme greed", "Brak opisu": "Description unavailable",
    "Aktualizacja źródła: ": "Source updated: ",
    "Źródło: FearGreedFlow": "Source: FearGreedFlow",
    "Fear & Greed Index jest chwilowo niedostępny.": "Fear & Greed Index is temporarily unavailable.",
    "Dane opóźnione": "Delayed data",
    "Futures ukryte podczas sesji regularnej indeksu.": "Futures hidden during the index's regular session.",
    "Brak dostępu do notowań: ": "Quotes unavailable: ",
    "Źródło: Investing.com — US Tech 100 Cash, US 500 Cash i powiązane futures CME. Wartości w punktach, czas CET/CEST. Futures podczas regularnej sesji rynku akcji: —. Dane mogą być opóźnione.":
        "Source: Investing.com — US Tech 100 Cash, US 500 Cash and related CME futures. Values in points, times in CET/CEST. Futures during regular US stock market hours: —. Data may be delayed.",
    "Trwa sesja regularna — notowania rozszerzone są ukryte.": "Regular session is open — extended quotes are hidden.",
    "Nie można potwierdzić statusu sesji — notowania rozszerzone są ukryte.": "Session status is unavailable — extended quotes are hidden.",
    "Przeciągnij, aby zmienić kolejność. Klawiatura: Alt + strzałka.": "Drag to reorder. Keyboard: Alt + arrow.",
    "Kliknij, aby posortować": "Click to sort",
    "Nie zapisano kolejności. Spróbuj ponownie.": "Column order was not saved. Please try again.",
    "Układ zmienił się w innej karcie. Spróbuj ponownie.": "Layout changed in another tab. Please try again.",
    "Pre-market i after-hours": "Pre-market and after-hours",
    "Brak dostępnych notowań": "No quotes available",
    "Yahoo · świeca 1 min (dane zastępcze)": "Yahoo · 1-minute bar (fallback)",
    "Yahoo · cena sesji": "Yahoo · session price",
    "Bezpośrednie ceny Yahoo; przy braku ceny oznaczone świece 1-minutowe. Czas w CET/CEST (Europe/Warsaw). Pre-market: zmiana względem poprzedniego zamknięcia. After-hours: względem zamknięcia tej sesji. Tylko dane z bieżącego dnia giełdowego; mogą być opóźnione. Wycena portfela używa cen sesji regularnej.":
        "Direct Yahoo prices; labeled 1-minute bars when a price is unavailable. Times in CET/CEST (Europe/Warsaw). Pre-market: versus the previous close. After-hours: versus that session's close. Only data from the current exchange date; delays are possible. Portfolio valuation uses regular-session prices.",
    "Login": "Username",
    "Wartość pozycji musi być dodatnią, skończoną liczbą.": "The position value must be a positive finite number.",
    "Moje<span>Portfolio": "My<span>Portfolio",
    "Moje portfolio": "My portfolio", "MojePortfolio": "MyPortfolio", "AKCJE USA": "US EQUITIES",
    "Logowanie do MojePortfolio": "Sign in to MyPortfolio",
    "Zaloguj się, aby przeglądać i modyfikować portfele.": "Sign in to view and edit your portfolios.",
    "Hasło": "Password", "Zaloguj się": "Sign in", "Wyloguj się": "Sign out", "Wyloguj": "Sign out",
    "Nieprawidłowy login lub hasło.": "Incorrect username or password.",
    "Nieprawidłowy login.": "Incorrect username.",
    "Zbyt wiele prób. Odczekaj minutę.": "Too many attempts. Please wait a minute.",
    "Nie można odczytać konfiguracji logowania.": "Unable to read sign-in configuration.",
    "Ustawienia portfela": "Portfolio settings", "Dane rynkowe": "Market data",
    "Odświeżaj co minutę": "Refresh every minute", "ceny w USD": "prices in USD",
    "Pozycje zapisane lokalnie w portfolio.json. Dane nie są synchronizowane z brokerem.":
        "Holdings are saved locally in portfolio.json. Broker synchronization is not enabled.",
    "Wszystkie portfele": "All portfolios", "Łączna wartość": "Total value",
    "Wartość rynkowa": "Market value", "Zmiana dzienna": "Daily change", "Zwrot od zakupu": "Total return",
    "Zmiana dzienna (USD)": "Daily change (USD)",
    "Zainwestowany kapitał": "Invested capital", "Posiadane akcje": "Holdings",
    "Względem zamknięcia sesji poprzedzającej datę ostatniego notowania. Wynik portfela ważony wartością pozycji na poprzednim zamknięciu.":
        "Compared with the prior session close. Portfolio change is weighted by holdings at the previous close.",
    "Zmiana wartości portfela względem zainwestowanego kapitału. Bez dywidend, prowizji i wpływu kursów walut.":
        "Return relative to invested capital, excluding dividends, fees and exchange-rate changes.",
    "pozycje": "holdings", "całości": "of total", "dzisiaj": "today",
    "Spółka": "Company", "Ticker": "Ticker", "Symbol": "Symbol", "Cena": "Price", "Kurs": "Price",
    "Co dziś zmieniło wartość portfela?": "What moved the portfolio today?",
    "Największy dodatni wkład": "Top positive contributors",
    "Największy ujemny wkład": "Top negative contributors",
    "Brak pozycji": "None",
    "Wpływ USD/PLN": "USD/PLN impact",
    "Dzienna zmiana w PLN": "Daily change in PLN",
    "Brakuje kursu USD/PLN dla tej sesji lub jego poprzedniego zamknięcia.":
        "The USD/PLN rate for this session or its previous close is unavailable.",
    "Do przeliczenia użyto historycznego zamknięcia USD/PLN z dnia":
        "Converted using the historical USD/PLN close for",
    "Wkład spółek w PLN po bieżącym kursie. Wpływ waluty względem poprzedniego zamknięcia USD/PLN.":
        "Stock contributions use the current exchange rate. The currency impact uses the previous USD/PLN close.",
    "Akcje": "Shares", "Liczba akcji": "Number of shares", "Średnia": "Average cost",
    "Średni zakup": "Avg. cost", "Wartość": "Value", "Udział": "Weight",
    "Średnia cena zakupu": "Average purchase price", "Zwrot %": "Return %",
    "Zwrot USD": "Return USD", "Wynik od zakupu": "Total return",
    "Wynik od zakupu (USD)": "Total return (USD)",
    "Widoczne kolumny": "Visible columns", "Dodaj kolumnę": "Add column",
    "Dodaj wybraną kolumnę": "Add selected column",
    "Wszystkie dostępne kolumny są już widoczne.": "All available columns are already visible.",
    "Widoczne kolumny — usuń × lub wybierz z listy": "Visible columns — remove × or select from the list",
    "Przywróć wszystkie kolumny": "Restore all columns",
    "Zmiany zapisują się automatycznie, osobno dla każdego portfela. Wybrany układ jest wspólny dla urządzeń korzystających z tej instalacji.":
        "Changes are saved automatically for each portfolio and shared across devices using this installation.",
    "Nie zapisano układu: ": "Layout was not saved: ", "Nie można odczytać układu kolumn: ": "Unable to read table layout: ",
    "Wszystkie kolumny ukryte. Wybierz kolumny w menu Widoczne kolumny.":
        "All columns are hidden. Choose columns in the Visible columns menu.",
    "Struktura portfela": "Portfolio allocation",
    "Edytuj pozycję": "Edit holding", "Wybierz pozycję": "Select holding",
    "Podaj łączną liczbę posiadanych akcji i aktualną średnią cenę zakupu. Zapis zastępuje poprzednie wartości.":
        "Enter the total number of shares and current average purchase price. Saving replaces the previous values.",
    "Zapisz zmiany": "Save changes", "Zapisano zmiany: ": "Changes saved: ",
    "Odśwież notowania": "Refresh prices", "Pobieranie notowań…": "Fetching prices…",
    "Wiadomości spółek": "Company news", "Odśwież wiadomości": "Refresh news",
    "Pobieranie wiadomości…": "Fetching news…",
    "Najnowsze nagłówki z ostatnich 7 dni · do 10 wiadomości · Yahoo Finance":
        "Latest English headlines from the past 7 days · up to 10 articles · Yahoo Finance",
    "Brak dostępu do wiadomości dla: ": "News unavailable for: ",
    "Brak aktualnych wiadomości dla spółek w portfelach.": "No recent English news for the companies in your portfolios.",
    "Ostatnie sprawdzenie: ": "Last checked: ", "odświeżanie co 10 min": "refreshes every 10 minutes",
    "artykuły mogą wymagać subskrypcji": "articles may require a subscription",
    "Nie można odczytać portfolio.json: ": "Unable to read portfolio.json: ",
    "Nie udało się pobrać wszystkich cen. Spróbuj odświeżyć notowania.": "Unable to fetch all prices. Try refreshing prices.",
    "Błąd aktualizacji: ": "Update failed: ",
    ". Wyświetlane są ostatnie kompletne dane; sprawdź czas pobrania na dole.":
        ". Showing the last complete data; check the fetch time below.",
    "Brak poprzedniego zamknięcia dla części spółek. Ich zmiana dzienna i suma portfela są niedostępne.":
        "Previous close is missing for some companies. Their daily change and the portfolio total are unavailable.",
    "Notowania dotyczą różnych sesji. Łączna zmiana dzienna jest niedostępna do czasu aktualizacji.":
        "Quotes refer to different sessions. Total daily change is unavailable until updated.",
    "Notowania starsze niż 20 minut: ": "Quotes older than 20 minutes: ",
    ". Rynek może być zamknięty lub dane dostawcy opóźnione.": ". The market may be closed or provider data delayed.",
    "Źródło i czas notowań": "Quote source and time", "Czas notowania (CET/CEST)": "Quote time (CET/CEST)",
    "Kurs (USD)": "Price (USD)",
    "Yahoo Finance (yfinance), ostatnia dostępna świeca minutowa sesji regularnej. Dane mogą być opóźnione. Po zamknięciu rynku widoczne jest ostatnie notowanie.":
        "Yahoo Finance (yfinance), latest available regular-session minute bar. Data may be delayed. The last quote remains after market close.",
    "pobrano": "fetched", "ceny mogą być opóźnione": "prices may be delayed",
    "Ten portfel nie ma pozycji.": "This portfolio has no holdings.",
    "Nieprawidłowy wybór kolumn.": "Invalid column selection.",
    "Nieprawidłowy plik układu kolumn.": "Invalid table layout file.",
    "Pozycja zmieniła się od otwarcia formularza. Odśwież stronę i spróbuj ponownie.":
        "This holding changed after the form was opened. Refresh the page and try again.",
    "Liczba akcji musi być dodatnią, skończoną liczbą.": "The number of shares must be a positive finite number.",
    "Średnia cena zakupu musi być dodatnią, skończoną liczbą.": "The average purchase price must be a positive finite number.",
}


LANGUAGE_COOKIE_NAME = "portfolio_language"
LANGUAGE_SECONDS = 365 * 24 * 60 * 60


def resolve_language(*values):
    return next((value for value in values if value in ("pl", "en")), "pl")


def language():
    return resolve_language(st.query_params.get("lang"), st.context.cookies.get(LANGUAGE_COOKIE_NAME))


_REPLACEMENTS = tuple(sorted(EN.items(), key=lambda pair: len(pair[0]), reverse=True))


@lru_cache(maxsize=1024)
def _english(text):
    if text in EN:
        return EN[text]
    # Dynamic captions include dates, symbols, and amounts; translate only UI fragments.
    for source, target in _REPLACEMENTS:
        text = text.replace(source, target)
    return text


def tr(text):
    return _english(text) if isinstance(text, str) and language() == "en" else text


def language_selector(key="ui-language"):
    inline = key == "ui-language"
    current = language()
    # A URL language change (including back/forward navigation) must update an
    # already mounted selector instead of being overwritten by its old value.
    url_key = f"language-url-{key}"
    if st.session_state.get(url_key) != current:
        st.session_state[key] = current
        st.session_state[url_key] = current
    with (nullcontext() if inline else st.container(horizontal=True, horizontal_alignment="right")):
        selected = st.selectbox("Język / Language", ["pl", "en"], index=None,
                                key=key, width=140 if inline else 170,
                                label_visibility="collapsed" if inline else "visible",
                                format_func=lambda code: "Polski" if code == "pl" else "English")
    if selected in ("pl", "en") and selected != current:
        st.query_params["lang"] = selected
        # Dialog widgets normally rerun only the dialog. Rebuild the whole UI
        # so its title, form labels and controls switch language together.
        st.rerun(scope="app")
