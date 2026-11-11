# 第八批 US-24 独立核对与正式执行

日期：2026-11-11。未提交、未 push。

## 断言复核

B8-01 已按 assignmentId 定位爸爸的 TaskCard，在该卡范围断言待审/驳回/重提/批准后的状态与进度，妈妈已完成的任务不能再替代爸爸卡的断言。B8-02 已读取实际客户端 balancesB，批准前按 dadId/momId 核对；批准后沿商城刷新、账户弹层入口核对爸爸 25、妈妈 5，没有断言前灌入目标单例值。

真实爸爸 token 驳回/批准，执行人界面提交/重提/查看历史；外人及另一发行人调用真实路由被拒。各阶段后端余额、流水和进度检查保留。数据库是临时 SQLite，不是 MySQL；发行人界面未被驱动，非真机或冷启动。

Claude 报告的正常副本及三项客户端变异结果已审阅，本次未独立重跑这些变异。后端变异是“尚未进行”，不是技术上不能进行：可以让 LPB_INT_BACKEND_DIR 指向临时后端副本，同时继续借用原解释器；无需改原仓库业务源码。本批不追加这一实验，不把未执行的变异列为通过。

## 正式映射与执行

已把草案 M-B-REAL-REVIEW 追加到 examples/mappings/task-b-001.mapping.yaml，旧三个条目全部保留。新条目 level=e2e、runner=flutter、companions=[backend-python]，一个 exact 联调用例覆盖七个单元；断言失败会连带这些覆盖单元，不冒充分步独立测试。

工作区 life-piggy-bank-us24 仅引用 TASK-B-001 故事与映射，配置在忽略的 .flowtree/workspaces.yaml。使用 pinned 环境、HOME、后端目录及绝对解释器路径绑定，保留 git 排除规则；pytest 的 ENVIRONMENT=test/DATABASE_URL 使用隔离配置，联调辅助自行生成临时 SQLite URL 与随机密钥。

命令：`.venv/bin/python -m cli.main workspace verify life-piggy-bank-us24 --mapped-only --json`，随后同工作区 status --json。

run：`run_20261111T084109_dfe3c13d`。四个条目全部完成，共 20 项通过（后端 1、既有客户端提交文件 12、模拟审批历史文件 6、新真实双账号联调 1），0 失败、0 跳过；七个单元 passed/current，未映射 0，verify/status 均退出 0，无证据完整性问题。逐次核对产物哈希及 changed_during_run。样本测试前后源码内容摘要一致。

## 页面数据核对

通过 FastAPI TestClient 读取 `/api/workspaces/life-piggy-bank-us24/stories/TASK-B-001?refresh=true`。七个单元自动化有效通过，旧后端/客户端/模拟审批条目与新联调条目都保留，相关条目 validity=current；规则仍 draft、七项人工未验收、complete=false。本次只验证页面接口数据，未另做浏览器点击测试。

当前页面详情可区分映射条目、测试名称及运行报告，但没有单独展示 mapping.level 标签；不能声称已新增专门的 backend/client/e2e 分层 UI。模拟审批测试的名称与真实联调条目的范围均保留，不将 Flutter runner 本身等同于真实联调。

审计目录 `.flowtree/reviews/b8-us24-codex/` 保存 verify/status、命令、源码前后摘要与 Web 响应。正式产物在 LPB `.flowtree/runs/run_20261111T084109_dfe3c13d/`，均不入库。

## 边界与下一步

故事补充了“待审、驳回和重提不增加有效进度、B 余额或 B 奖励流水”的不变量；零余额、25/5 是夹具，不是产品默认规则。规则确认、Q-10、人工验收不由本次测试代签。

只刷新 TASK-B-001 四个入口，没有重跑其他故事或 FlowTree 框架全量回归，不能把本次七项当前通过外推为其他故事仍有效。下一步整理两个仓库的本批提交清单，不提交运行产物、本机配置或用户流程图。
