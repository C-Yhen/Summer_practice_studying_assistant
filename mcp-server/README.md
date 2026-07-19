# 学习助手 MCP Server

该服务把学习平台的受控 REST API 暴露为 18 个 MCP 工具。只读工具直接调用；写工具采用“两阶段确认”：首次调用只返回预览与 5 分钟有效的确认令牌，用户明确同意后，第二次携带相同参数和令牌才执行。

```powershell
cd mcp-server
python -m venv .venv
.venv\Scripts\pip install -e .
$env:BACKEND_BASE_URL = "http://localhost:8000/api/v1"
$env:MCP_CONFIRMATION_SECRET = "replace-with-random-secret"
.venv\Scripts\smart-learning-mcp
```

生产环境应传入后端签发的有效访问令牌，并由后端再次校验用户与资源所有权。确认令牌只证明“用户确认前后参数未变化”，不能替代 JWT、后端权限校验和幂等约束。

## 日历工具

日历工具操作的是 StudyPilot 本地日历，并未接入 Outlook 或 Google Calendar。创建、修改和删除均先请求后端预览，由后端签发短时确认令牌；用户确认后，第二次调用必须使用相同参数并显式携带该令牌。ICS 导出用于手动导入第三方日历。

MCP 审计会递归清理输入、输出和错误信息中的确认令牌、访问令牌、Authorization、JWT、刷新令牌和 API Key；后端审计接口会再次执行同样的防御性清理。审计发送失败不会覆盖真实工具结果。

## 测试

```powershell
cd mcp-server
.venv\Scripts\pip install -e ".[test]"
.venv\Scripts\pytest -q
```

真实后端联调为显式用例：

```powershell
$env:BACKEND_BASE_URL = "http://127.0.0.1:8000/api/v1"
$env:ROUND13_LIVE_MCP = "1"
.venv\Scripts\pytest -q tests/test_live_calendar_tools.py
```
