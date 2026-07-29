@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [StudyPilot] 正在停止服务（保留数据库、Redis 与上传资料数据卷）...
docker compose down
if errorlevel 1 (
  echo 停止失败。请确认 Docker Desktop 正在运行后重试。
  pause
  exit /b 1
)

echo 服务已停止，数据卷已保留。请勿使用 docker compose down -v，除非确认需要删除全部本地数据。
pause
endlocal
