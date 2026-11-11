# 伴随运行时独立复验：暂缓正式映射

日期：2026-11-11。核对实现并新增独立测试 `tests/independent/test_b7_companions_review.py`；没有改实现方文件、正式映射或样本项目，没有提交。完整测试日志在本机忽略目录 `.flowtree/reviews/b7-companions-codex/pytest.txt`。

实际结果：实现方 15 项通过；独立 5 项中 3 项通过、2 项失败。合计 18 通过、2 失败，0 跳过；失败恰为以下两条反例。

## B7-01：只读探测实际写出字节码

`probe_python` 设置 PYTHONDONTWRITEBYTECODE=1，但命令使用 `-I`，Python 会忽略 PYTHON* 环境变量。用临时 venv、无副作用的 sitecustomize.py 实测：探测成功返回摘要，同时在被探测 site-packages 写出 __pycache__/sitecustomize.*.pyc。CLI/Web 的只读重检也会调用同一探测。

独立反例比较探测前后全部文件内容，而非仅检查项目目录。建议在解释器参数中显式增加 `-B`，不能只依赖环境变量。修复后该反例须通过。

## B7-02：绑定按验证器 cwd 解释相对路径

`_binding_problem` 对实际环境变量值执行 abspath/expanduser。相对路径会按 FlowTree 进程 cwd 解释；样本辅助以 backendDir 作为 Python 子进程 workingDirectory，同一字符串可能指向另一个解释器。当前检查仍可能认为与声明路径一致，违背“探测 A、执行 A”。

独立反例使用一个真实临时 venv：声明路径绝对、绑定值相对，验证器 cwd 与客户端 cwd 不同；当前绑定检查错误地接受。建议要求实际绑定值为明确的绝对路径（不接受 ~ 或相对路径），再进行绝对路径比较；或统一解析并把解析后的同一个值真正传给子进程。不要仅在比较时标准化。

## 已核对与下一步

独立正例覆盖绝对路径匹配/不匹配/缺失、依赖元数据变化导致摘要变化、SQLite 版本存在、无 companions 时原 RuntimeProbe 原样返回。运行实现方 15 项作为聚焦回归。

请 Claude 修复两项，不改独立测试或放宽断言。两项通过后才将 TASK-A-002 草案移入正式映射，在独立 pinned 联调工作区执行并核对页面；当前五个单元保持未映射，不手工点亮。尚未验证 FlowTree 超时下的后端清理；不能将其列为已通过。

## 修复后独立复跑

B7-01/02 修复后，实现方 15 项与原独立 5 项共 20 项通过，0 失败、0 跳过（41.04 秒）。Codex 随后为 pytest 同类探测补上显式 -B，新增独立只读检查 1 项通过。没有修改原两条失败断言。正式 US-23 执行见 `BATCH_07_US23_INDEPENDENT_ACCEPTANCE.md`。
