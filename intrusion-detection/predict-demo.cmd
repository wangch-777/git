@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m ml.cli predict --input data/processed/demo_input.csv --output data/processed/demo_predictions.csv
pause
