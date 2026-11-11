# 第九批独立核对：验证层级与运行器展示

日期：2026-11-11。范围：共享视图输出 level/runner、详情与场景证据行标签、对应聚焦测试。未改执行器、schema、样本业务源码或 examples。

## 核对结果

`_entry_out` 从当前故事的映射条目读取 level/runner，不从测试结果或运行器名称推断层级；字段只用于展示，没有修改状态聚合。映射内容本身变化仍按既有条目摘要规则使旧证据过期，不承诺“改 level 后旧证据仍有效”。

详情明确标注“映射声明”，保留范围说明、完整测试名、报告入口、最近结果、证据有效性与规则/人工独立状态。未新增执行、签字或写接口。既有的无执行记录条目不列出测试名称的行为未变。

## 实际验证

Codex 复跑 `tests/implementation/test_b2_stories_api.py` 与 `test_b2_page_render.py`：48 通过、0 失败、0 跳过，含真实 Chrome 渲染。仅有既有 TestClient 弃用提示；没有重跑无关业务或框架全量回归。

另用本机真实 `life-piggy-bank-us24` 工作区启动临时只读 Web 服务，核对实际 API，而非仅更改 pytest 夹具的 level：M-B-REVIEW=backend/pytest；M-B-CLIENT-SUBMIT 与 M-B-CLIENT-HISTORY=client/flutter；M-B-REAL-REVIEW=e2e/flutter。七个单元仍 passed/current，complete=false。

内置浏览器不可用（发现列表为空），使用独立临时 Chrome 配置回退验证。真实 Chrome 渲染 STEP-03 与 STEP-04 抽屉，分别核对后端/联调和客户端/联调标签、声明边界、完整 nodeid、最近结果及当前有效性；保存 DOM 和截图，并查看 STEP-04 截图确认布局。没有以截图代替交互测试；本次没有另跑真实点击交互。

样本源码、已存在证据文件的内容校验和及 git status 前后一致。临时 Web 服务与 Chrome 已退出。审计日志、API 响应、DOM 与截图位于忽略目录 `.flowtree/reviews/b9-levels-codex/`。

## 后续范围

本任务通过后及时做一个本地提交，不 push。当前两个真实联调仍未覆盖发行人审批界面；下一步由 Claude 只读核对该界面的驳回/批准入口和真实会话切换，提交最小联调方案。复用既有隔离后端和运行时绑定，不扩大框架、不把 API 审批证据写成发行人界面已验收。规则确认和人工验收继续单独保留。
