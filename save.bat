@echo off
chcp 65001 >nul
cd /d "%~dp0"
git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo This folder is not a Git repository. Initialize it or copy files into your repository first.
  pause
  exit /b 1
)
git check-ignore -q .env
if errorlevel 1 (
  echo ERROR: .env must be ignored and must not be tracked.
  pause
  exit /b 1
)
echo Review changes before staging. This script does not push or publish.
git status --short
echo Use: git add followed by explicit file paths, then git commit.
pause
