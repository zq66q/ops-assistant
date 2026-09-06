# 巡检健康探测把running误判为故障

症状：
- 后台健康巡检将健康服务(如 openclow /health 返回 status=running、components 均 ok)误报为异常 incident(open)

根因：
- 健康判定只识别 status==ok，未接受 running/healthy/up 等常见健康态，导致把正常服务判为故障

处置步骤：
1. 用健康词集合判定：status 属于 {ok,running,healthy,up,ready,active,alive,pass,operational} 即视为健康
2. 同时校验 components 各子项均为健康；HTTP<400 且无显式非健康 status 才判健康
3. 连接失败/超时/5xx/显式非健康 status 才判故障
4. 修复后巡检自动关闭对应 incident 并计入 MTTR(发现到恢复)

来源：用户沉淀
