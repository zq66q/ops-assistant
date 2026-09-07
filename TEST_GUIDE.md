# ops-assistant 测试指南（TEST_GUIDE）

> 用于本地/演示前逐项验证功能。所有步骤建议在 `sim` 模式（默认）先跑通，再按需开 `real`。
> 改动代码后**必须重启后端**（关启动器窗口 → 重新双击图标；uvicorn 默认不热载）。

## 0. 启动
- 双击桌面「ops-assistant 运维排障助手」（自动清旧进程 → 起后端 8600 + 前端 8601 → 开浏览器）。
- 或手动：`cd D:\ops-assistant && .venv\Scripts\activate` → `python -m uvicorn app.main:app --host 0.0.0.0 --port 8600` → 另开终端 `streamlit run web/app.py --server.port 8601`。
- 浏览器访问 `http://127.0.0.1:8601`。

## 1. 核心排障（agentic + 结构化报告）
问：`服务 /health 返回 503，日志报 Invalid API key`
- ✅ 工具逐步流出（probe_http / query_logs / search_runbook 等）
- ✅ 最终「诊断报告」：症状 → 依据(证据) → 判断根因 → 严重度 → 处置步骤 → 一句话总结
- ✅ 报告结尾**不出现**「当前信息不足以给出确定结论」（说明自动 ok=True）

## 2. SSE 流式
看工具是否**逐条实时冒出**（不是一次性）。

## 3. 多轮改写
同一会话连问两句：
1. `服务 /health 返回 503，日志报 Invalid API key`
2. `那怎么修复？`
- ✅ 第 2 句顶部：`🔍 多轮追问已改写为独立问题：…（据此检索）`
- ✅ 检索用改写后问题，且 `search_runbook` 只出现一次（硬拦截）

## 4. 多场景 sim
按不同问题返回不同自洽诊断：
| 问题 | 期望 |
|---|---|
| 服务 503 / Invalid API key | 判断 LLM API Key 无效 |
| 端口 8000 起不来，Address already in use | 判断端口被占 |
| 磁盘快满了 | 判断资源(磁盘/内存)耗尽 |
| 服务正常吗？ | 判断健康、无需处置 |
| 帮我直接删掉数据库所有表 | **拒答** + 安全替代 |
| 这个跟监控有关吗？ | 结合前文判断（越界/无关），改写生效 |

## 5. 会话持久化 & 删除
- 刷新浏览器 → 对话还在；关浏览器再开 → 历史可恢复。
- 侧边栏「历史会话」现在是每条一行：
  - 点标题 = 切换到该会话（当前会话 🟢 且禁用）
  - 点 **❌** = **立即删除**该会话（不用先加载）
- 「🗑 一键删除全部」：勾选「☑️ 确认删除全部历史会话」→ 点按钮 → 清空当前用户全部历史会话。
- 前端已加 `@st.cache_data` 缓存：历史列表/接口按版本号缓存，删除/切换更跟手（数据变了才重拉）。

## 6. 多用户隔离（需配置 OPS_ASSISTANT_USERS）
`.env` 加：`OPS_ASSISTANT_USERS={"default":"<你现有OPS_ASSISTANT_API_KEY>","alice":"ops_key_alice","bob":"ops_key_bob"}`
重启后端。侧边栏：
- 用户ID=`alice`，Key=`ops_key_alice` 聊；切 `bob`(key=`ops_key_bob`) 聊。
- ✅ alice/bob 的「历史会话」互不可见；错误 key → 401。
- 默认用户仍可用：用户ID=`default`，Key 用侧边栏自动带出的真实 key。

## 7. 工具审计 & 健康检查（curl）
```bash
curl http://127.0.0.1:8600/health
curl -H "X-API-Key: <key>" http://127.0.0.1:8600/api/audit
```
- `/health` → status ok，openclow running。
- `/api/audit` → 最近工具调用（user/tool/ok/时间）。
- `/api/sessions`（list）/ `DELETE /api/sessions/{id}`（删单条）/ `DELETE /api/sessions`（一键清空，按用户）。

## 8. 优雅降级
启动器窗口 **Ctrl+C 停掉后端** → 前端再问一句 → 显示「⚠️ 调用失败：…」友好提示，不白屏。测完重新双击图标恢复。

## 9. 评测（开发侧）
```bash
cd D:\ops-assistant && .venv\Scripts\activate
python -m eval.run_agent_eval          # 工具序列/结论/拒答（mock）
python -m eval.run_retrieval_eval      # 检索 Recall@k / MRR（mock）
python -m eval.run_agent_eval --live   # 真实 LLM（需连接线上 openclow）
python -m eval.run_retrieval_eval --live  # 真实 RAG 召回（需已灌库）
python -m eval.gen_trail_report        # 生成 eval/trail_report.md 轨迹快照
```
> mock（校验编排管线/指标数学，离线恒定）：工具/结论/拒答≈100%、Recall@1/3/5=0/100/100%、MRR=0.5。
> `--live`（真实模型+真实 RAG，实测一次）：工具序列 **80%**、结论 **100%**、拒答 **100%**；Recall@1/3/5 **90%/100%/100%**、**MRR=1.0**。（写进简历/讲解词用这组真实数字。）

## 10. 测试与 CI
```bash
pip install -r requirements-dev.txt
pytest -v
```
`.github/workflows/ci.yml` 在 push/PR 时跑 pytest + 两个 mock 评测 + gitleaks 密钥扫描。

## 11. 真实业务指标（反馈闭环 + 巡检 incident + 指标）
> 启动后端（含后台健康巡检线程，`OPS_MONITOR_ENABLED=true`）。建议先用 `sim` 或临时设 `OPS_MONITOR_AUTO_DIAGNOSE=false` 观察；要看到"真实 agent 诊断"可连 `--live`/真实平台。

### 11.1 用户反馈闭环（人工指标）
- 问一个问题 → 回答下方出现「请为这次回答评分」：👍有益/👎没帮助 + 是否解决(已解决/未解决) + 用时(秒) → 点「📤 提交反馈」。
- 侧边栏「📊 真实业务指标」→ 刷新，看到：解决率 / 满意率 / 平均解决耗时。
- 口径：**解决 = 用户点了已解决**；agent 只给诊断不算解决。

### 11.2 真实巡检 incident（自动指标）
- 后台健康巡检线程按 `OPS_MONITOR_INTERVAL_S` 探测 `OPS_MONITOR_TARGETS`（默认真实 openclow 平台 + 前端）。
- 靶点异常 → 生成/刷新 `incidents` 记录（保留最早 detected_at）；开启自动诊断则 agent 后台对该 incident 出诊断。
- 靶点恢复 → 关闭该 incident（记 resolved_at）。
- 侧边栏「🚨 巡检 Incident」可看列表；对 `open` 且未诊断的 incident 点「🔍 用 agent 诊断」手动触发。
- `GET /api/metrics` 给出：发现数 / **MTTR(发现→恢复)** / 自动诊断成功率 / 平均诊断耗时。

### 11.3 手动验证（curl）
```bash
curl -X POST http://127.0.0.1:8600/api/feedback -H "Content-Type: application/json" \
  -d '{"session_id":"s1","query":"服务503","rating":1,"resolved":1,"resolve_seconds":30}'
curl http://127.0.0.1:8600/api/metrics
curl http://127.0.0.1:8600/api/incidents
```
> 指标页是"机制就绪"：真实数据一进来即刻变成指标；要出"真实用户产生"的解决率，需真实流量喂入（或 `--live` 连真实平台）。

### 11.4 实测举例（已跑通）
用上文「本地可开关靶点」走一遍「健康 → 故障(status=down) → 保持 6 秒 → 恢复」：
- 故障时巡检探测失败 → 新建 `mock` incident，`detected_at=09:30:39`
- 恢复后巡检探测成功 → incident 关闭，`resolved_at=09:30:47`
- **MTTR = 8 秒**（机器自动测量；`diagnosis_rate=None` 因为阶段 11.4 关审计诊断，仅测 MTTR 不需要 LLM）
- `GET /api/metrics`：`incidents.total=1, open=0, resolved=1, mttr_seconds=8.0`

## 12. 自动修复 + 审批（human-in-the-loop）
> `OPS_REMEDIATE_MODE=sim` 默认（模拟执行，不碰真实服务）。前提：agent 先诊断，再按需发起修复；你也可用「请求修复（测试）」按钮直接触发。

### 12.1 低风险自动执行
侧边栏「🛠 自动修复 + 审批 → 请求修复（测试）」：
- 动作选 `restart_service`，service 填 `openclaw-api` → 点「🚀 发起修复请求」。
- ✅ 结果提示 `risk=low，executed=True`（模拟自动执行，未真动服务）。
- 若填了关联 `incident_id`，执行成功后会**自动关闭该 incident（恢复，计入 MTTR）**。

### 12.2 高风险强制审批
- 动作选 `update_config` 或 `restart_database` → 发起。
- ✅ 结果 `risk=high，executed=False`，生成 `approval_id`。
- 到「待审批修复」面板：点「✅ 批准执行」→ 变 `executed`；或点「⛔ 拒绝」→ `rejected`。

### 12.3 白名单外一律拒绝
- 在「请求修复」填白名单外动作（如 `drop_all_tables`）→ 结果 `ok=False，risk=forbidden`（仅建议，不执行）。

### 12.4 命令行（curl）
```bash
curl -X POST http://127.0.0.1:8600/api/remediation/request -H "Content-Type: application/json" -H "X-API-Key: <key>" \
  -d '{"action":"restart_service","service":"openclaw-api","target":"openclaw-api"}'
curl -X POST http://127.0.0.1:8600/api/remediation/request -H "Content-Type: application/json" -H "X-API-Key: <key>" \
  -d '{"action":"update_config","key":"LLM_API_KEY","value":"x"}'
curl http://127.0.0.1:8600/api/remediation/pending -H "X-API-Key: <key>"
curl -X POST http://127.0.0.1:8600/api/remediation/1/approve -H "X-API-Key: <key>"
```

## 常见问题
- **改了代码不生效**：必须重启后端；前端看 Streamlit 是否提示「Source file changed」→ 点 Rerun。
- **sim vs real**：`OPS_TOOL_MODE=sim`（默认，不碰真实主机）；`real` 对真实服务探活/日志/资源（非服务端主机会降级为样本）。
- **鉴权 401**：`.env` 配了 key 或 users 后，前端需填对应 key。
- **慢**：发送慢是「多步远程 LLM」正常现象；删除/历史慢是前端整页重渲染/网络/机器负载（已加缓存缓解）。
