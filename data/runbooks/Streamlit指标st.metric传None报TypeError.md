# Streamlit指标st.metric传None报TypeError

症状：
- 前端侧边栏指标展示报 TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'

根因：
- 后端在无已解决/未解决判断时返回 resolve_rate=None；前端 fb.get('resolve_rate',0) 在 key 存在且值为 None 时仍返回 None，导致 None*100 崩溃

处置步骤：
1. 前端展示前对 None 归一化：值为 None 时显示占位符 '—'，避免 None*100
2. 无法用 .get(key, default) 兜底 None，需显式判断 (v if v is not None else ...)
3. 后端约定：无足够数据时该指标返回 null，由前端兜底展示

来源：用户沉淀
