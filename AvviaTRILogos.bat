@echo off
REM TRILogos — avvio rapido (doppio clic)
cd /d "%~dp0"
python gui.py
if errorlevel 1 (
  echo.
  echo ERRORE: assicurati che Python sia installato e che le dipendenze siano presenti.
  echo Per installare le dipendenze: pip install -r requirements.txt
  pause
)