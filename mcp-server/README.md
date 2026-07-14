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

生产环境应配置后端服务令牌，并由后端再次校验 `user_id` 与资源所有权。确认令牌只证明“用户确认前后参数未变化”，不能替代 JWT、后端权限校验和幂等约束。
