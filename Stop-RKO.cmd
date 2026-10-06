@echo off
cd /d "%~dp0"
docker compose --profile "*" stop
if errorlevel 1 pause
