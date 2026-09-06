# ops-assistant —— 智能运维排障助手（agentic）

基于 openclow 平台的独立业务应用，演示「平台 + 业务应用」解耦，并把这层业务应用升级成**能动手排障的 agent**：

- **openclow**：负责 LLM、RAG 检索、嵌入、鉴权、监控等通用 AI 能力（底座）
- **ops-assistant**：负责 Agent 工具循环（探活/日志/资源/服务状态/手册检索）、Query 改写、SSE 流式、会话持久化、工具审计、结构化诊断报告与评测
- **自我成长（learning loop）**：agent 遇到知识库没有的问题会诚实说明「知识库中无相关信息」；你解决后一键沉淀成 runbook 并灌入知识库，下次即可检索回答。**已在真实环境验证「未覆盖 → 沉淀 → 再问可答」闭环。**

核心变化（相较最初的文档问答 demo）：从「检索 → 复述」一条单回路，升级为「**收集证据 → 下结论**」的工具调用 agent，并配套可自证效果的评测与测试/CI。

## 架构

```
用户问题 / 追问
   → ① Query 改写 + 取会话历史
   → ② Agent 工具循环（最多 N 轮）
        ┌─ LLM 决策 ─→ 调用工具 ─→ 拿证据 ─→ 再决策
        │   工具：probe_http / query_logs / check_resources
        │         / service_status / search_runbook(RAG)
        │   工具双后端：sim(固定样本) / real(真实服务)
   → ③ 结构化诊断报告（症状/证据/根因/严重度/处置/置信度/来源）
   → ④ 会话持久化 + 工具审计 → SSE 流式 / REST 返回
```

## 目录

| 路径 | 说明 |
|---|---|
| `agent/` | 工具调用循环、诊断报告、LLM 工具客户端 |
| `tools/` | 5 个排障工具 + 注册表 + 执行器 + sim 样本 |
| `app/` | FastAPI 后端（chat/chat_stream/sessions/audit）+ 编排 + 会话/审计 |
| `web/` | Streamlit 前端（SSE 流式展示工具轨迹） |
| `data/runbooks/` | 真实排障手册语料（灌进 openclow RAG） |
| `eval/` | 四类评测（工具序列 / 结论 / 拒答 / 检索 recall@k+MRR） |
| `tests/` | pytest 单元/集成测试（sim + mock，无外部依赖） |

## 快速开始

```bash
cd D:\ops-assistant
copy .env.example .env   # 填入 OPENCLOW_API_KEY
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m eval.ingest_corpus          # 灌入 语料 + 排障手册
uvicorn app.main:app --host 0.0.0.0 --port 8600   # 后端
streamlit run web/app.py --server.port 8601        # 前端（另开终端）
```

## 关键配置（.env）

| 变量 | 说明 | 默认 |
|---|---|---|
| `OPENCLOW_BASE_URL` / `OPENCLOW_API_KEY` | openclow 平台 | `http://localhost:8000` / 空 |
| `OPS_TOOL_MODE` | `sim` 固定样本；`real` 打真实服务 | `sim` |
| `OPS_AGENT_TOOL_PROTOCOL` | `json`（兼容现有 /chat/raw）；`native`（原生 function-calling，需 openclow 升级） | `json` |
| `OPS_AGENT_MAX_STEPS` | agent 最大工具轮数 | 6 |
| `OPS_TARGET_HEALTH` / `OPS_TARGET_UI` | real 模式排障靶点 | `http://103.236.98.200:8000/health` 等 |
| `OPS_SESSION_DB_PATH` / `OPS_AUDIT_DB_PATH` | 会话 / 审计库 | `./data/*.db` |
| `OPS_ASSISTANT_API_KEY` | 业务侧自身鉴权 | 空 |
| `OPS_MONITOR_ENABLED` | 是否开启后台健康巡检（产生真实 incident） | `true` |
| `OPS_MONITOR_INTERVAL_S` | 巡检间隔（秒） | `60` |
| `OPS_MONITOR_AUTO_DIAGNOSE` | 巡检发现异常是否自动调 agent 诊断 | `true` |
| `OPS_MONITOR_TARGETS` | 巡检靶点 `{"name":"url"}`（JSON） | 探 openclow 平台 + 前端 |

## API 端点

| 端点 | 说明 |
|---|---|
| `GET /health` | 健康检查（含 openclow 状态） |
| `POST /api/chat` | 同步排障（返回结构化 report + 工具轨迹） |
| `POST /api/chat/stream` | SSE 流式（`session` / `tool` / `final` / `error` 事件） |
| `GET /api/sessions` | 会话列表 |
| `GET /api/sessions/{id}/history` | 会话历史 |
| `GET /api/audit` | 工具调用审计记录 |
| `POST /api/feedback` | 用户对回答的反馈（👍/👎 + 是否解决 + 用时） |
| `GET /api/metrics` | 真实业务指标聚合（解决率/满意率/平均耗时/MTTR/诊断率） |
| `GET /api/incidents` | 巡检发现的最新 incident 列表 |
| `POST /api/incidents/{id}/diagnose` | 用 agent 对某 incident 做一次诊断 |
| `POST /api/incidents/clear` | 清空 incident 记录（巡检/调试，重置指标面板） |

## 评测

```bash
# agent 编排管线校验（工具序列/结论/拒答，mock 用，CI 无外部依赖）
python -m eval.run_agent_eval
# 检索召回（Recall@k / MRR，mock 验证指标数学）
python -m eval.run_retrieval_eval
# 真实 LLM 驱动（需连接线上 openclow + LLM 余额）
python -m eval.run_agent_eval --live
# 真实 RAG 检索召回（需已灌入 runbooks + 语料）
python -m eval.run_retrieval_eval --live
```

四类指标：工具序列正确率、结论正确率、拒答正确率（工具/结论/拒答），以及检索 Recall@1/3/5 与 MRR（RAG 质量）。正常必给结论、越界必拒答，不做关键词命中。

### 实测结果（真实 `--live`，连线上 openclow + 已灌库）
| 指标 | 结果 |
|---|---|
| 工具序列正确率 | **80%**（4/5） |
| 结论正确率 | **100%** |
| 拒答正确率 | **100%** |
| 检索 Recall@1 / @3 / @5 | **90% / 100% / 100%** |
| MRR | **1.000** |

> 说明：`--live` 用真实大模型驱动 agent 决策、真实 RAG 检索；数值为实测一次。`mock` 模式只用于验证编排管线与指标数学（CI 可离线跑，结果恒定）。

把 agent 轨迹快照渲染成可读 Markdown（面试展示用）：

```bash
python -m eval.run_agent_eval          # 先跑评测生成 agent_results.json
python -m eval.gen_trail_report        # -> eval/trail_report.md（症状/工具序列/根因/处置）
```

## 测试与 CI

```bash
pip install -r requirements-dev.txt
pytest -v
```

`.github/workflows/ci.yml` 在 push/PR 时跑 `pytest` + mock 评测。

## 真实业务指标（可落地，不只是一次 demo）

除了"能回答问题"，这套还提供**可量化的经营/运维指标**，把系统从"技术原型"变成"有度量的系统"。指标分两类来源：

### 1. 用户反馈闭环（人工指标）
每次回答下方有「👍/👎 + 是否解决 + 用时(秒)」，存入 `feedback` 表，`GET /api/metrics` 聚合：
- **解决率** = 标记「已解决」的反馈数 / 有明确 resolved 判断的反馈数（agent 给诊断不算解决，用户点了才算）。
- **满意率** = 好评数 / 已评好差评的反馈数。
- **平均解决耗时** = 用户从提问到点「已解决」的平均秒数。

### 2. 真实巡检 / incident（自动指标，不依赖真人）
后台健康巡检线程（`app/monitor.py`）定时探测 `OPS_MONITOR_TARGETS` 里的真实靶点（openclow 平台 / 前端等）：
- 探测**异常** → 记录/刷新一个 `incidents` 记录（保留最早 `detected_at` 以计算真实 MTTR）；开启 `OPS_MONITOR_AUTO_DIAGNOSE` 时后台自动调 agent 对该 incident 产出诊断。
- 探测**恢复** → 关闭该 incident（写 `resolved_at`）。
- 指标：**巡检发现数 / MTTR（发现→恢复）/ 自动诊断成功率 / 平均诊断耗时**。

### 指标口径（面试会追问）
- **解决** = 用户点「已解决」；agent 只给诊断不算解决。
- **MTTR（停摆时长）** = 从巡检发现异常到靶点恢复健康的时长（自动化、非人工）。
- **诊断成功率** = agent 对 incident 给出有效诊断（report.ok）的比例。

> 说明：指标展示的是**机制就绪**——真实数据一进来即自动变成可汇报指标。若要得到"真实用户产生"的业务指标，仍需要真实流量/真实故障数据喂入（或用 `--live` 连真实平台）。这一块正是从"演示"跨到"可落地"的关键。

## 安全性

- `.env` 已 gitignore；`.env.example` 与语料中的真实 Key 已替换为占位符。
- **若你的 Key 曾出现在公开仓库/历史里，请立即在服务器 `.env` 轮换并重启。**
- **多用户身份由凭证决定**：配置 `OPS_ASSISTANT_USERS={"alice":"key_a","bob":"key_b"}` 后，后端按 `X-API-Key` 解析出真实 user_id（不再信任客户端自报的 `X-User-Id` 头）。只有一个 `OPS_ASSISTANT_API_KEY` 时归属 `default`；都未配置时才退回 `X-User-Id`（仅本地开发）。
- 工具默认只读（探活/日志/资源/状态）；破坏性操作（重启/改配置）仅建议、agent 拒绝对越界请求直接动手。
- CI 里跑 **gitleaks 密钥扫描**，防止明文密钥被提交。

## openclow 的配套改动

为使业务应用能用**原生 function-calling**（可选），openclow 的 `src/api/models.py` 与 `src/api/routes/chat.py` 增补了 `tools`/`tool_choice` 透传与 `tool_calls` 返回（纯增量）。默认 `json` 协议无需此改动即可运行。
