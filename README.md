# ops-assistant —— openclow 运维排障助手

基于 openclow 平台构建的独立业务应用，演示“平台+业务解耦”架构：

- **openclow**：负责 LLM、RAG 检索、鉴权、监控等通用 AI 能力
- **ops-assistant**：负责聊天界面、多轮会话、Query 改写、业务评测

## 快速开始

1. 复制环境变量模板：
   ```bash
   cp .env.example .env
   # 编辑 .env，填入你的 openclow 地址和 API Key
   ```

2. 安装依赖：
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. 灌入运维知识库（语料在 `data/corpus/`）：
   ```bash
   python -m eval.ingest_corpus
   ```

4. 启动后端：
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8600
   ```

5. 启动前端（另一个终端）：
   ```bash
   streamlit run web/app.py
   ```

## 目录说明

| 目录 | 说明 |
|---|---|
| `app/` | FastAPI 后端 + openclow 调用封装 + 编排逻辑 |
| `web/` | Streamlit 聊天界面 |
| `data/corpus/` | 运维知识语料，用于 ingest 进 openclow 知识库 |
| `data/sessions.db` | SQLite 会话持久化（自动生成） |
| `eval/` | 评测集与跑分脚本 |
| `deploy/` | systemd 服务文件（API + UI 各一个） |

## 生产就绪项

相较于最初的 demo 版本，已补齐 5 个短板：

1. **已部署到服务器**：通过 `deploy_ops_assistant.py` 一键上传到 `/opt/ops-assistant`，systemd 托管 API（8600）和 UI（8601）两个服务。
2. **会话持久化**：`app/session.py` 从内存 dict 改为 SQLite，后端重启不丢历史。
3. **API Key 鉴权**：业务应用自身增加 `OPS_ASSISTANT_API_KEY`，FastAPI 校验 `X-API-Key`；未配置时不校验，方便本地开发。
4. **评测集扩展**：新增 10 条口语化/错别字/跨文档问题，共 34 题，基线准确率仍保持 100%。
5. **优雅降级**：openclow 平台不可用时，聊天接口返回友好提示，不再直接 500。

## 评测

```bash
python -m eval.run_eval
```

结果会打印准确率，并写入 `eval/results.json`。

### 基线结果（2026-08-25）

| 类型 | 题目数 | 准确率 |
|---|---|---|
| 直问式 | 19 | **100%** |
| 追问式 | 15 | **100%** |
| 整体 | 34 | **100%** |

追问式问题依赖 Query 改写：业务应用先根据对话历史把"那前端呢？"改写成"备案期间如何通过IP和端口访问openclow的前端界面？"，再去做 RAG 检索，从而召回准确答案。

新增 10 条口语化/错别字/跨文档问题（如"openclow 咋跑起来的啊？""swagger 上那个锁点不动怎么回事？"），用于验证真实问法下的召回稳定性。
