@echo off
cd /d "%~dp0"
if exist "secrets\cloudflare-tunnel.token" (
  docker compose --profile cloudflare up -d bot adminer cloudflared
  if not errorlevel 1 docker compose --profile cloudflare up -d --force-recreate --no-deps cloudflared
) else (
  docker compose up -d bot adminer
)
if errorlevel 1 pause
