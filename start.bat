@echo off
echo Starting Stylo Berlin MVP...
call venv\Scripts\activate
uvicorn main:app --reload
