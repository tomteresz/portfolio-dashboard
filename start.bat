@echo off
setlocal
cd /d "%~dp0"

if not exist ".env\Scripts\activate.bat" (
    echo The .env environment is missing. See the installation steps in README.md.
    pause
    exit /b 1
)

call ".env\Scripts\activate.bat"
if errorlevel 1 (
    echo Failed to activate the .env environment.
    pause
    exit /b 1
)

if not "%PORTFOLIO_DEMO%"=="1" if not exist "data\auth.json" (
    python -m portfolio_app.credentials
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

streamlit run app.py
if errorlevel 1 pause
endlocal
