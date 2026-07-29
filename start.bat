@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [StudyPilot] 正在检查 Docker 环境...
where docker >nul 2>&1
if errorlevel 1 (
  echo 未找到 Docker CLI。请安装 Docker Desktop，并确认 docker 已加入 PATH。
  goto :error
)

docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Engine 未运行。请先启动 Docker Desktop，等待 Engine running 后重试。
  goto :error
)

if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo 已从 .env.example 创建 .env。
  echo .env.example 提供 Qwen 配置模板。使用真实 Qwen 请在本机 .env 填写 LLM_API_KEY。
  echo 没有 Qwen Key 时，请将 .env 中的 LLM_PROVIDER 改为 mock；不要提交 .env 或真实密钥。
) else (
  echo 检测到已有 .env，将直接使用现有本机配置（不会覆盖）。
)

echo [StudyPilot] 正在检查 Compose 配置...
docker compose config --quiet
if errorlevel 1 goto :error

echo [StudyPilot] 正在构建并启动 frontend、backend、worker、postgres、redis...
docker compose up -d --build
if errorlevel 1 goto :error

echo.
docker compose ps
echo.
echo 启动命令已完成。请等待 backend 显示 healthy 后访问：
echo   前端: http://localhost:8080
echo   健康检查: http://localhost:8000/health
echo   Swagger: http://localhost:8000/docs
echo 若服务未正常启动，请执行：docker compose logs --tail=200 backend worker
goto :end

:error
echo.
echo 启动失败。请根据上方信息排查；窗口将保持打开。
pause
exit /b 1

:end
pause
endlocal
