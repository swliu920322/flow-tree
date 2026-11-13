# US-23 故事与断言核对

日期：2026-11-11。只读审查新增联调测试与辅助配置；未独立复跑 Claude 的七项测试或变异实验。本次新增故事 YAML，未改框架、样本代码、旧故事或正式映射，未提交。

## 故事文本

新增 `examples/stories/task-a-002.story.yaml`，独立 ID `TASK-A-002`，来源为 LPB `USER_STORY_MAP.md` 的 US-23。保留原 `TASK-A-001` 的一次目标示范，不用新场景覆盖旧证据。

三个主步骤：登录查看零进度 → 第一次进度 1/2、未完成且不发奖 → 第二次完成、仅一条奖励流水。两个分支：第一次已知成功后重新加载页面；完成后重复提交不重复发奖。共五个自动验证单元。奖励 15、每日任务、零关系和初始零积分是本例夹具，不升级为普遍产品规则。故事文本对照来源及断言成立，不等于负责人确认或人工验收，规则维度仍为 draft。

## 断言与措辞

新增测试确实核对首次 A=0/无流水、第二次 A=15/恰一条流水（delta/balance_before/balance_after）、账本对账和第三次提交 409 后余额/流水不变；未独立复跑，不将实现方七项通过写成 Codex 实测。

“重进”实际代码通过 Navigator.push 创建一个新 TasksPage，随后 pop 返回原页；原页没有被销毁。因此仅证明新页面重新读取进度且没有额外提交，不能声称销毁重建原页面。故事 CASE-01 按此收窄。不把空白凭证、并发或未知结果恢复加入本故事的已验证分母；也未核对 MySQL 并发用例是否提供对应证明。

## 映射与执行上下文

后续映射可使用 runner=flutter、level=e2e、cwd=.、argv=[flutter, test, test_integration/real_backend_two_checkins_test.dart]，tests 使用 testWidgets 的完整 exact 名称。timeout_s 建议 300，须另用临时草稿验证 FlowTree 超时的进程清理路径。

在独立 pinned 工作区配置中设置非机密路径：

```yaml
execution_context:
  mode: pinned
  pinned_path: /Users/liushengwei/flutter/bin:/usr/bin:/bin
  env:
    LPB_INT_BACKEND_DIR: /Users/liushengwei/taylors_project/Life-Piggy-Bank/backend
    LPB_INT_PYTHON: /Users/liushengwei/taylors_project/Life-Piggy-Bank/backend/venv/bin/python
    PYTHONDONTWRITEBYTECODE: '1'
  env_from_host: [HOME]
```

继承现有工作区的 git_excludes_file，使样本 .flowtree 产物不进入源码指纹。机器路径仅放本机忽略配置，不写进可移植故事和映射。样本辅助代码用以上两个环境变量解析后端目录和解释器，字面路径适用，不必用 env_from_host 读取这些固定路径。数据库 URL 和随机密钥由隔离测试生成。

## 页面与未完成事项

现有工作区读取整个 examples/stories，因此新故事可由页面发现；未建立正式映射，五个单元均应为 unmapped。不得将直接 flutter test 的成功手工写成 FlowTree 通过。

正式点亮前仍需绑定后端 Python 运行时及依赖：同一只读探测参与执行前后和状态重检，变更失效、探测失败未知。现有 Flutter runtime digest 没有这一覆盖；日志记录版本不替代绑定。Claude 下一步先提交最小设计，不直接扩展框架；并修正文档中原页销毁、MySQL 已有证据等未证实表述。Q-SAV-NAV-001 继续保留，测试不代签规则确认或人工验收。
