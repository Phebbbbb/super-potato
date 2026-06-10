@echo off
cd /d C:\Users\23182\smart-tax\backend
C:\Program Files\Python312\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
