# API 鉴权与 Swagger 测试

## 鉴权方式

openclow 使用 X-API-Key 请求头鉴权：

```
X-API-Key: <your_api_key>
```

API Key 以 `oc_` 开头，存储在 `/opt/openclow/.env` 的 `OPENCLAW_API_KEYS` 变量中。

## Swagger 中使用

1. 打开 `http://103.236.98.200:8000/docs`
2. 点击右上角 Authorize
3. 输入 API Key（不需要 `oc_` 前缀之外的格式，直接粘贴完整 key）
4. 关闭弹窗后，带锁的接口会自动带上 X-API-Key

## 认证失败表现

未带 Key 或 Key 错误时，接口返回 401：

```json
{"detail": "Invalid or missing API Key"}
```

## 安全注意

- API Key 属于敏感信息，不要写在公开仓库里
- 如果怀疑泄露，立即在服务器 .env 中更换，并重启服务
- 前端页面不能直接暴露 Key，必须由后端转发

## 常用测试接口

- `POST /chat`：同步对话
- `POST /chat/stream`：SSE 流式对话
- `POST /rag/ingest`：文本入库
- `POST /rag/search`：知识库检索
- `POST /memory/search`：记忆搜索
