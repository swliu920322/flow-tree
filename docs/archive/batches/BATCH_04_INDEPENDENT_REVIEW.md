**最新状态：B4-01及两项客户端断言缺口均已关闭。第四批约定范围通过；正式整批51 passed，16/19单元本次有效，剩余3项离页重进未映射，规则与人工验收未完成。下文保留历史记录，最新证据见末节。**

# 第四批设计检查与独立反例

2026-11-10，Codex。基线eabda3a，dirty工作区。结论：runner职责分离、单一机器来源声明、pinned与只读运行时探测方向合理；**B4-01协议校验未通过，暂不提交或发布正式客户端通过证据**。

## 实际复验

- 原47项独立断言继续通过。
- 新增6项：完整名称含`::`、success+skip、hidden=false的加载失败三个正向控制通过；以下三个异常事件流被错误接受。
- 完整独立批次：**50 passed、3 failed、0 skipped，45 warnings，46.94秒**。不与初次6项试跑重复计数。
- Claude的407项是实现方结果，本次未重复：先修可快速复现的协议问题，再安排必要回归与真实客户端映射。
- 证据：`.flowtree/reviews/b4-codex-2026-11-10/`，含基线哈希、命令、原始日志、JUnit及临时项目。

## B4-01：异常协议流被接受为completed/passed

位置：flowtree/runners/flutter_runner.py 的 analyze。
独立文件：tests/independent/test_b4_review.py。
三个参数化反例：

1. `done_before_start`：同一测试的testDone出现在testStart之前，仍completed/passed。
2. `second_session_start`：会话中出现第二个start，仍completed/passed。
3. `malformed_error`：测试已有error事件，但缺少协议要求的isFailure字段；判定代码只检查isFailure是否非None，结果忽略这条错误并通过。

原因：当前分多轮扫描收集testStart/testDone/error，再配对，丢失了事件先后约束；error字段不完整时又被当作没有错误。

修复要求：按流维护会话及每个测试ID的生命周期；唯一start、唯一最终done、testDone只能结束已开始的测试。允许不同测试正常交错，不要强行串行。已出现的error不能因字段缺失被静默丢弃；协议关键字段缺失/类型错误或状态矛盾应为执行error，保留原始报告。正常skip、加载伪测试、同文件重名等既有语义不变。

Claude只修这组问题，补自己的回归；不修改Codex断言求绿、不扩大业务修复范围。修复交付后Codex再完成正式客户端映射与最小真实执行。

## 映射边界

五项仍是候选，须按实际断言逐项确认。已读零关系创建、家庭凭证入口及克制重放相关测试；不能仅凭测试标题或弹窗已打开，就宣称“分类、金额、备注全部可输入”已验证。断言不足时保留未映射或明确待补，不弱化故事换覆盖率。

本次没有改examples/、业务源码、夹具或用户流程图，没有运行样本部署或真实库，没有提交。

## 修复后复验与正式映射

2026-11-10，B4-01关闭。Codex实际复跑：解析器45+映射校验48，共 **93 passed**；完整独立断言 **53 passed**，均0 failed/skipped。未重跑未受本次修复影响的315项。实现方18项真实Flutter反向测试仍是其证据，不冒充本轮独立执行。

本轮正式接入3项：
- SAV-001.STEP-02：M-SAV-CLIENT-PENDING，证明待确认请求保存Key、分类与金额。
- TASK-A-001.STEP-01：M-A-CLIENT-CREATE，零关系用户进入A任务创建并提交。
- TASK-B-001.STEP-01：M-B-CLIENT-SUBMIT，从待办打开凭证输入并提交。

原项目三个文件实际执行：savings_controller **23 passed**，task13_onboarding_and_relationship_direction **5 passed**，family_tasks_closed_loop **12 passed**，合计 **40 passed**。三个attempt均completed/exit 0、changed_during_run=false，无证据问题，原始产物哈希匹配；后续workspace status仍有效。

运行：`run_20261110T115623_f246f858`。原项目`.flowtree/runs/<run>/<story>/<entry>/`保存原始证据；命令、JSON、JUnit和摘要在FlowTree本机`.flowtree/reviews/b4-fixes-codex-2026-11-10/`。本机工作区为`life-piggy-bank-client`，其配置已忽略、不入库。

19个单元中已映射 **14**、未映射 **5**。本客户端上下文本轮有效3，其余已有11个映射因上下文不同保持待更新；映射数量不等于当前通过数量。规则草稿、人工未验收维持原状。

两个候选未自动接入：
- SAV-001.STEP-01：候选证明弹窗打开，但没有充分直接断言分类、金额、备注三个输入均可操作。
- SAV-001.CASE-02：候选分别证明同Key、分类重放、保存金额或提示金额；尚不足以直接证明实际发送的完整原payload（尤其金额、备注）不被替换。测试标题不替代断言。

这属于候选断言待补强，不是已证实业务缺陷。下一批交Claude在样本既有测试中补两项精确断言：编辑三个字段后检查提交参数；超时后改输入再重试，检查实际调用的Key/分类/金额/备注仍等于原请求。Codex再核对并映射，不弱化故事、不改业务源码求绿。

原项目源码前后哈希一致，Git状态仍仅原有`.flowtree/`；未pub get、升级、部署或触碰真实库。FlowTree产品和实现测试在本轮执行期间未改；只增加映射、独立反例和说明。未stage/commit/push。

## 新增客户端测试的独立核对与整批刷新

已读样本新增的 `test/savings_submission_wire_test.dart`：捕获真实HttpSavingsRepository传给拦截http.Client的请求，复制头和值及请求体字符串，断言编辑三项后完整JSON相等、重放Key及请求体相等、独立新意图使用新Key。断言足以补齐SAV-001.STEP-01与CASE-02，予以正式映射。验证边界是客户端请求构造，不是真实HTTP服务端或TLS网络。

新增正式M-SAV-CLIENT-WIRE，六个精确名称来自真实事件流，covers仅STEP-01、CASE-02；STEP-02保留原正式M-SAV-CLIENT-PENDING。临时M-WIRE不进入正式映射，避免错误叠加旧stale结果。原测试文件保留在样本项目，未提交。

因新增测试改变全仓指纹，本次重新运行**全部9个正式映射入口**，同一pinned上下文、同一新工作区基线：**51 passed、0 failed/skipped**（后端5项、Flutter46项），命令均干净。run=`run_20261110T121733_36ce89d9`。随后只读workspace status与Web API均确认**16个单元本次passed、3个unmapped**；无证据问题，产物哈希匹配、运行期间源码未变。

原始证据在样本`.flowtree/runs/run_20261110T121733_36ce89d9/<story>/<entry>/`。本机详细命令、完整JSON、Web汇总、source-before/after哈希在FlowTree`.flowtree/reviews/b4-wire-codex-2026-11-10/`。

未映射的3项均为各故事STEP-04的离开后重进；规则仍draft、人工仍none，整体complete=false。不得称为完整业务或真实设备验收。

保留新增测试文件，不改业务源码、已有测试和夹具。原项目本次运行前后源码一致，Git仅原有`.flowtree/`及新增测试文件未跟踪。框架实现与此前93/53复验哈希一致，未重复框架全量回归；本次51项是新业务基线，不能与旧批次累计冒充一次运行。两个仓库均未stage/commit/push。
