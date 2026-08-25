# RAG 知识库与记忆的区别

## RAG 是什么

RAG（Retrieval-Augmented Generation）= 检索增强生成。

流程：用户问题 → 去向量库检索相关文档片段 → 把片段作为参考信息一起给 LLM → LLM 生成回答。

openclow 中的 RAG：

- 入库：`POST /rag/ingest` 或 `POST /rag/upload`
- 检索：场景内自动检索，或外部应用调用 `/rag/search`
- 存储：向量库（ChromaDB）

## 记忆是什么

记忆用于保存用户画像、跨会话的偏好、长期事实等。

- 写入：业务逻辑主动写入
- 查询：`POST /memory/search`
- 存储：SQLite `data/memory.db`

## 关键区别

| | RAG | Memory |
|---|---|---|
| 内容 | 文档、知识库 | 用户相关的事实、偏好 |
| 存储 | 向量库 | SQLite |
| 使用方式 | 按问题检索 | 按用户检索 |
| 例子 | 部署文档、API 说明 | 用户是张经理、偏好简洁回答 |

## 常见问题

### /rag/ingest 返回 chunks:0 是失败了吗？

不一定。openclow 会对相同 source 做去重：如果内容没变，会跳过入库，返回 `chunks: 0`。日志里通常会看到 `ingest skipped: content unchanged`。

### /memory/search 返回空怎么办？

先确认 memory 表里有没有这个用户的数据。memory 不会自动产生，需要业务代码主动写入。如果库里没有数据，返回空是正常的。

### RAG 检索不到内容怎么办？

1. 确认语料已入库（`GET /rag/status` 看 sources）
2. 确认问题与语料匹配，必要时做 query 改写
3. 调大 top_k 或开启 rerank
4. 检查 chunk 大小是否切得太碎
