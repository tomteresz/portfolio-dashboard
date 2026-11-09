@echo off
setlocal
cd /d "%~dp0"

if not exist ".env\Scripts\activate.bat" (
    echo The .env environment is missing. See README.md.
    pause
    exit /b 1
)
call ".env\Scripts\activate.bat"
if errorlevel 1 exit /b 1

if not exist ".streamlit\demo" mkdir ".streamlit\demo"
copy /y "examples\demo_portfolio.json" ".streamlit\demo\portfolio.json" >nul
if errorlevel 1 (
    echo Failed to prepare the demo data.
    pause
    exit /b 1
)

set "PORTFOLIO_PATH=%CD%\.streamlit\demo\portfolio.json"
set "LAYOUT_PATH=%CD%\.streamlit\demo\layout.json"
set "SESSION_DB_PATH=%CD%\.streamlit\demo\sessions.sqlite3"
set "LOG_DIR=%CD%\.streamlit\demo\logs"

echo DEMO - fictional holdings, live provider data.
echo Each launch restores the sample holdings. Use your regular sign-in credentials.
streamlit run app.py
if errorlevel 1 pause
endlocal
