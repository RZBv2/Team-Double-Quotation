@echo off
echo Installing required packages...
pip install keyboard pywin32 Pillow
echo.
echo Creating database...
python -c "import sqlite3; print('Database ready')"
echo.
echo Starting Exam System...
python main.py
pause