@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Защита от утечки ключа: .env должен быть в .gitignore
git check-ignore -q .env || (echo ОШИБКА: .env не исключён из Git, коммит отменён & exit /b 1)
if "%~1"=="" (set /p MSG=Что сделано за этот час: ) else (set "MSG=%~1")
git add -A
git commit -m "%MSG%"
git push
