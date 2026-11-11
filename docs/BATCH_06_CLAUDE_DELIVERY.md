# 第六批交付记录（Claude）：客户端 ↔ 真实后端联调（隔离测试，尚未接正式映射）

> 本文保留写作时点的过程状态；最新执行与清理复验以 [US-23 独立验收记录](BATCH_07_US23_INDEPENDENT_ACCEPTANCE.md) 为准。原映射草案已由 `examples/mappings/task-a-002.mapping.yaml` 取代。

日期：2026-11-11。只在 Life-Piggy-Bank 新增 `test_integration/`（未跟踪）：`support/real_backend.dart`（隔离后端辅助）与 `real_backend_a_task_test.dart`。未改业务源码、已有测试、夹具；未接 FlowTree 正式映射；未提交、未 push。

## 1. 真实 / 非真实

| 真实 | 不是真实（如实） |
|---|---|
| Flutter 登录界面、任务页、控制器、HTTP 仓储、AuthService；回环网卡上的真实 HTTP；后端业务代码、真实 Alembic 迁移后的库、真实 JWT、真实账本与对账接口 | **数据库是 SQLite（临时文件），不是 MySQL**；MySQL 的并发/锁/隔离语义不在本测试内，也不由它推断（未核对既有后端测试是否证明过，本报告不作此声明） |
| | 账号与任务由测试经真实后端 API 创建，不是界面驱动 |
| | 运行在 `flutter test` 环境，非真机/桌面冷启动；"重进"是同进程内新开一个任务页面再返回（原页面仍保留），不是页面销毁重建，也不是杀进程恢复 |

## 2. 结果

`flutter test --no-pub` 最小环境（`env -i`）：**6 passed、0 failed**（1 个联调主用例 + 5 个隔离/清理用例）。`flutter analyze` 对新目录：1 条 warning（`setMockInitialValues` 的 visible-for-testing，已有测试同样用法）与 2 条 info，无 error。

主用例顺序：API 建零关系用户 + A 类 15 分任务 → **真实登录界面登录** → 任务页显示后端返回的任务与「+15 A」 → 打卡/确认提交 → 界面「已完成」，客户端 A 积分 15（经 `refreshProfile`） → 账户弹层显示 15 → 后端侧独立核对（`/auth/me`=15、对账平衡、任务 done） → **重进两次**（先于重复提交） → 最后故意重复提交得 409。

请求计数来自**后端自己的结构化访问日志**（不是客户端日志）：
- 提交 POST：重进前恰好 `[200]`；两次重进均断言 `GET /tasks/my` 与 `GET /auth/me` 计数增加、提交 POST 计数不变；重进结束仍 `[200]`、后端积分仍 15；
- 之后的故意重复提交：`[200, 409]`，积分仍 15、账本平衡。两类请求按顺序分开断言，互不混淆。

## 3. 隔离与清理

- 子进程环境仅 `PATH/ENVIRONMENT=test/DATABASE_URL/随机 SECRET_KEY/...`，`includeParentEnvironment:false`；`DATABASE_URL` 守卫要求是系统临时目录下的 SQLite（含 macOS `/tmp→/private/tmp` 解析；有单测）。
- **先登记再迁移/启动**：临时目录最先创建并登记；`start()` 任何阶段失败都走同一个幂等 `stop()`，异常携带 `tempDirPath` 供核对。
- 后端是测试的**普通子进程**（不脱离进程组），清理只按 PID 发 SIGTERM→超时 SIGKILL，不向进程组发信号。
- 就绪判定：必须看到**自己进程**输出 `Uvicorn running on 127.0.0.1:<port>` 与 `Application startup complete`，再 GET `/docs` 为 200（原始 socket，避免测试绑定把 `HttpClient` 桩成 400）；端口被占（子进程提前退出）则换端口，最多 3 次；所有等待均有期限。
- 全局状态：`HttpOverrides`、`ApiService.instance`、会话存储、`customClient`、当前用户在 `setUp` 保存、`tearDown` 恢复。
- 页面有持续动画，`pumpAndSettle` 会超时，故用有限次 `pump` 与有期限的 `untilFound`。

已验证：启动失败（解释器不存在 / 迁移失败，临时目录已删）、端口被占后换端口且接管者是自己的进程、停止后进程退出+端口拒绝连接+目录已删且 `stop()` 幂等；在**副本**里往主用例注入断言失败 → 测试失败后无遗留 uvicorn 进程、无 `lpb_int_*` 目录。
**尚未验证**：FlowTree 超时（进程组 kill）路径下是否同样无残留——需等正式映射后用小 `timeout_s` 的草稿映射实测；运行中途机器断电类场景不在范围。

## 4. 问题与修正（运行中发现）
1. 测试绑定把 `dart:io HttpClient` 桩成 400：就绪探测改为原始 socket。
2. DATABASE_URL 守卫在 macOS 上对不存在的子目录未解析符号链接，误拒绝合法路径：改为解析最近的已存在祖先。
3. `pumpAndSettle` 在任务页超时：改为有限 pump。

## 5. 第 5 点：运行时绑定方案（仅方案，未实现）

**问题**：联调结果依赖后端解释器及其依赖，但现有 FlutterRunner 的 runtime digest 只覆盖 Flutter SDK/pubspec.lock/package_config，换后端 venv 或升级依赖不会使旧联调证据失效。仅写进日志不满足"变化即失效"。

**方案**：在通用层引入"伴随运行时"（companion runtime）声明，映射/执行上下文里可写：
```yaml
companion_runtimes:
  - name: lpb-backend
    interpreter: /abs/path/backend/venv/bin/python   # 或相对工作区
    files: [backend/requirements.txt, backend/alembic/versions]  # 参与摘要的文件/目录
```
1. **同一个只读探测函数**：对声明的解释器取 realpath、`--version`、已安装依赖清单（固定的只读子命令，最小环境，不联网、不安装），再加声明的文件内容摘要，合成 `companion_digest`。执行前、执行后、`story status`/Web 只读复核都调用它。
2. **并入基线**：`companion_digest` 作为运行时摘要的独立字段进入基线与证据记录；执行前后不一致 → 本次运行作废（与现有 runtime 变化同处理）；复核时与证据不一致 → `stale`；探测失败 → `unknown`，不静默放过。
3. **只实现一次**：放在公共 runner/baseline 层，通过 runner 适配器接口提供"声明哪些伴随项"；探测命令由声明给出的解释器 + 固定参数组成（Python 的 `pip list` 之类放在配置示例中，核心不出现 Python 特例分支）。
4. **已知限制**：当前 Flutter runtime digest 不覆盖后端 venv；在此方案落地前，联调证据不应声称"依赖变化会自动失效"。

等待 Codex 审核本方案与上述测试后，再接正式映射；Q-SAV-NAV-001、规则确认与人工验收仍单独保留，不由本测试代签。
