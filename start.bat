@echo off
setlocal

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

streamlit run app.py
if errorlevel 1 pause
endlocal
