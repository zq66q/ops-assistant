# 业务场景：ops-assistant 与 openclow 的关系

## 定位

- **openclow**：企业级 AI Agent 能力底座（L1~L7）
- **ops-assistant**：基于 openclow 的独立业务应用，专注 openclow 自身运维排障

## 解耦方式

ops-assistant 不修改 openclow 源码（除平台通用能力，如 `/rag/search`），只通过 API 调用：

- `/chat`：LLM 对话与 query 改写
- `/rag/search`：检索运维知识库
- `/rag/ingest`：灌入运维语料

## 为什么把业务放在外面

1. 平台保持通用，不被某个业务污染
2. 业务可以独立迭代、独立部署
3. 未来多个业务场景共享同一个 openclow 底座
4. 面试时能讲清楚“平台 + 业务应用”架构边界

## 多轮 RAG 与 Query 改写

ops-assistant 的典型流程：

1. 用户提问（可能是追问，如“那前端呢？”）
2. 业务应用根据历史把问题改写成独立问题
3. 用改写后的问题调用 `/rag/search` 检索
4. 把原始问题 + 检索结果一起给 `/chat` 生成回答

这就是企业里“多轮 RAG + Query 改写”的落地方式。
