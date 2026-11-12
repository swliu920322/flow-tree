/* FlowTree 故事验收页面 (只读)。所有请求均为 GET; 页面不执行测试, 也不写签字或验收记录。
   状态全部来自后端的领域计算, 这里只负责排版与措辞。所有动态文本都经 textContent 写入。 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = { workspaces: [], ws: null, stories: [], story: null, detail: null,
                  expanded: new Set(), opts: { ids: false, all: false, risk: false } };

  // ---------------------------------------------------------------- 工具
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) {
      if (kid == null || kid === false) continue;
      el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  // replaceChildren 不会展开数组也不会过滤空值 (会把 null 渲染成文字), 统一经此函数填充
  function fill(el, ...kids) {
    el.replaceChildren(...kids.flat(Infinity).filter((k) => k != null && k !== false)
      .map((k) => (k.nodeType ? k : document.createTextNode(String(k)))));
  }
  const short = (s, n = 12) => (s ? String(s).replace(/^sha256:/, "").slice(0, n) : "—");
  function fmtTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString("zh-CN", { hour12: false });
  }
  async function api(path) {
    const r = await fetch(path, { headers: { Accept: "application/json" } });
    if (!r.ok) {
      let msg = r.statusText;
      try { msg = (await r.json()).detail || msg; } catch (_) { /* ignore */ }
      throw new Error(`${r.status} ${msg}`);
    }
    return r.json();
  }
  function notice(msg) { $("notice").textContent = msg || ""; }
  function store(k, v) { try { localStorage.setItem("ft." + k, v); } catch (_) { /* 不可用时不影响页面 */ } }
  function load(k) { try { return localStorage.getItem("ft." + k); } catch (_) { return null; } }

  // ---------------------------------------------------------------- 措辞
  const RESULT = { passed: "通过", failed: "失败", error: "执行错误", blocked: "环境阻塞", not_run: "未执行",
                   running: "运行中", unmapped: "未映射", skipped: "跳过", xfailed: "已知缺陷(xfail)",
                   xpassed: "意外通过(xpass)", missing: "缺失" };
  // 映射声明的验证层级: 只说明这条证据"在哪一层、用什么运行器"验证, 不代表所有角色界面、真机或生产环境已验收
  const LEVEL = { code_review: "代码审查", backend: "后端验证", client: "客户端验证", e2e: "联调" };
  const LEVEL_NOTE = "验证层级由映射声明，只说明这条证据所在的层和运行器；仅凭客户端或联调条目，不能说明所有角色界面、真机或生产环境已验收。";
  const levelText = (e) => (e.level ? (LEVEL[e.level] || e.level) : "未声明");
  const VALIDITY = { current: "有效", stale: "待更新", unknown: "无法确认" };
  const ASPECT = { story: "故事内容", mapping_entry: "映射条目", env_id: "环境标识", worktree: "工作区代码",
                   runtime: "运行时与依赖", verifier: "验证器版本", environment: "环境变量配置", context: "执行上下文策略" };
  const ASPECT_STATE = { same: "一致", changed: "不同", unknown: "无法确认" };
  const KIND = { validation: "输入校验", recovery: "恢复", boundary: "边界", permission: "权限", concurrency: "并发" };

  function lastResults(u) {
    return u.entries.filter((e) => e.has_evidence && e.last_result)
      .map((e) => `${RESULT[e.last_result] || e.last_result}`).join(" / ");
  }
  function outdated(u) {
    return u.automation === "not_run" &&
      u.entries.some((e) => e.has_evidence && (e.validity === "stale" || e.validity === "unknown"));
  }
  function autoBadge(u) {
    switch (u.automation) {
      case "passed": return { t: "通过", c: "ok", tip: "本次基线下该场景映射的全部测试通过" };
      case "failed": return { t: "失败", c: "bad", tip: "映射的测试出现真实断言失败" };
      case "error": return { t: "执行错误", c: "bad", tip: "执行/收集/解析故障、证据损坏或测试标识缺失；不是产品断言失败" };
      case "blocked": return { t: "环境阻塞", c: "warn", tip: "已知环境前置缺失，未能执行" };
      case "running": return { t: "运行中", c: "info", tip: "" };
      case "unmapped": return { t: "未映射", c: "", tip: "尚未接入 FlowTree 映射。这不表示项目缺少测试，也不是业务缺陷" };
      default:
        return outdated(u)
          ? { t: "待更新", c: "warn", tip: `存在历史结果(${lastResults(u)})，但不适用于当前上下文，不计为本次通过` }
          : { t: "未执行", c: "", tip: "已映射，但还没有执行结果" };
    }
  }
  function dimBadges(u) {
    const a = autoBadge(u);
    const rule = u.rule === "pending"
      ? { t: "待确认", c: "warn", tip: `被未决问题阻塞：${u.blocked_by.join(", ")}` }
      : { t: "草稿", c: "", tip: "尚无规则确认记录" };
    const human = { none: "未验收", pass: "已通过", reject: "已驳回", na: "不适用" }[u.human] || u.human;
    const impl = { unchecked: "未检查" }[u.implementation] || u.implementation;
    // 就近原则: 机器给出的结论(实现/自动验证)放一组, 只能由人完成的(规则确认/人工验收)放另一组, 用留白+边框+"需要你"区分
    const ruleTodo = u.rule !== "confirmed" ? " todo" : "";
    const humanTodo = u.human === "none" ? " todo" : "";
    return h("div", { class: "dims" },
      h("div", { class: "dimgroup sys" },
        h("span", { class: "glabel", text: "系统" }),
        h("span", { class: "dim", title: "实现检查尚无来源" }, h("b", { text: "实现" }), impl),
        h("span", { class: "dim " + a.c, title: a.tip }, h("b", { text: "自动验证" }), a.t)),
      h("div", { class: "dimgroup human" },
        h("span", { class: "glabel" }, h("span", { class: "mark", "aria-hidden": "true", text: "✋" }), "需要你"),
        h("span", { class: "dim " + rule.c + ruleTodo, title: rule.tip }, h("b", { text: "规则" }), rule.t),
        h("span", { class: "dim " + (u.human === "pass" ? "ok" : u.human === "reject" ? "bad" : "") + humanTodo, title: "只有真实的人工操作才会改变这里" },
          h("b", { text: "人工" }), human)));
  }
  function evidenceLine(u) {
    const evs = u.entries.filter((e) => e.has_evidence);
    if (!evs.length) return null;
    return h("div", { class: "evid" }, h("span", { class: "glabel", text: "系统证据" }), evs.map((e) => {
      const v = e.corrupt ? "证据记录损坏" : (VALIDITY[e.validity] || "—");
      const diff = e.aspects ? Object.entries(e.aspects).filter(([, x]) => x !== "same").map(([k, x]) => `${ASPECT[k] || k}${ASPECT_STATE[x]}`) : [];
      return h("div", { class: "erow" }, h("span", { class: "chip", title: LEVEL_NOTE, text: levelText(e) }),
        h("span", {}, `最近执行 ${fmtTime(e.started_at)} · 结果 ${RESULT[e.last_result] || "—"} · 证据${v}${diff.length ? "（" + diff.join("、") + "）" : ""}`),
        h("span", { class: "sid", text: ` ${e.entry} ${short(e.run_id, 24)}` }));
    }));
  }
  function branchChips(sum) {
    const chips = [];
    const add = (n, text, cls) => { if (n) chips.push(h("span", { class: "chip " + cls, text: `${text} ${n}` })); };
    add(sum.bad, "失败/错误/阻塞", "bad");
    add(sum.outdated, "待更新", "warn");
    add(sum.never_run, "未执行", "");
    add(sum.automation.unmapped, "未映射", "");
    add(sum.automation.running, "运行中", "info");
    add(sum.rule_pending, "规则待确认", "warn");
    add(sum.automation.passed, "通过", "ok");
    return chips;
  }

  // ---------------------------------------------------------------- 渲染
  function renderTabs() {
    const nav = $("storyTabs");
    nav.replaceChildren(...state.stories.map((s) => h("button", {
      type: "button", "aria-current": s.id === state.story ? "true" : null, title: s.id,
      onclick: () => selectStory(s.id),
    }, s.title)));
  }

  function renderHead(d) {
    const t = d.totals, s = d.summary;
    const sysChips = [
      h("span", { class: "chip", text: `已定义 ${t.total} 个场景` }),
      h("span", { class: "chip " + (t.automation.passed ? "ok" : ""), text: `本次通过 ${t.automation.passed}` }),
      t.bad ? h("span", { class: "chip bad", text: `失败/错误/阻塞 ${t.bad}` }) : null,
      t.outdated ? h("span", { class: "chip warn", text: `待更新 ${t.outdated}` }) : null,
      t.never_run ? h("span", { class: "chip", text: `未执行 ${t.never_run}` }) : null,
      h("span", { class: "chip", text: `未映射 ${t.automation.unmapped}` }),
    ];
    const humanChips = [
      h("span", { class: "chip todo", text: `规则待确认 ${t.rule_pending}` }),
      h("span", { class: "chip todo", text: `规则仍为草稿 ${t.total - t.rule_pending}` }),
      h("span", { class: "chip todo", text: `人工未验收 ${t.human_unverified}` }),
    ];
    const reasons = h("ul", {}, [
      `${t.total - t.automation.passed} / ${t.total} 个场景没有“本次有效”的自动验证通过结果（含未映射、未执行、待更新）`,
      t.rule_pending ? `${t.rule_pending} 个场景被待确认问题阻塞` : null,
      "规则确认记录尚未支持，规则全部保持草稿",
      `${t.human_unverified} 个场景尚无人工验收`,
    ].filter(Boolean).map((r) => h("li", { text: r })));
    const extra = [];
    if (d.command_failures.length) {
      extra.push(h("div", { class: "verdict", style: "background:var(--bad-bg);color:var(--bad)" },
        "最近一次真实命令存在失败（与逐场景结果分开呈现）",
        h("ul", {}, d.command_failures.map((c) => h("li", {
          text: `${c.entry} 退出码 ${c.exit_code}；未映射的失败：${Object.keys(c.unmapped_nonpass).join(", ") || "无"}` })))));
    }
    if (d.evidence_problems.length) {
      extra.push(h("div", { class: "verdict", style: "background:var(--bad-bg);color:var(--bad)" },
        "证据完整性问题（相关尝试按执行错误处理，不会显示为通过）",
        h("ul", {}, d.evidence_problems.map((p) => h("li", { text: p })))));
    }
    $("storyHead").replaceChildren(h("div", { class: "card head" },
      h("h1", {}, d.story.title, h("span", { class: "sid", text: d.story.id })),
      h("div", { class: "meta", text: `${d.story.actor} · ${d.story.goal}` }),
      h("div", { class: "verdict" }, s.complete ? "已完成" : "整体未完成", reasons),
      h("div", { class: "panels" },
        h("section", { class: "panel sys" }, h("h2", { text: "系统自动验证" }),
          h("p", { class: "panel-note", text: "自动化的结果，只读；不能代替人的确认" }), h("div", { class: "counts" }, sysChips)),
        h("section", { class: "panel human" }, h("h2", {}, h("span", { class: "mark", "aria-hidden": "true", text: "✋" }), "需要你处理"),
          h("p", { class: "panel-note", text: "这几项只能由负责人确认，自动化不会代签" }), h("div", { class: "counts" }, humanChips))),
      extra));
  }

  function renderContext(d) {
    const c = d.context, o = c.validity_overview, r = c.recheck;
    const body = h("dl", {},
      h("dt", { text: "检查时间" }), h("dd", { text: fmtTime(c.checked_at) }),
      h("dt", { text: "证据有效性" }), h("dd", { text: `有效 ${o.current} · 待更新 ${o.stale} · 无法确认 ${o.unknown}（按映射条目计）` }),
      h("dt", { text: "项目" }), h("dd", { text: c.project_root }),
      h("dt", { text: "解释器" }), h("dd", { text: c.python || "未配置" }),
      h("dt", { text: "执行上下文" }), h("dd", { text: `${c.execution_context.mode === "pinned" ? "固定环境(pinned)" : "继承宿主环境(inherit)"}；声明变量 ${(c.execution_context.env_names || []).join(", ") || "无"}；取自宿主 ${(c.execution_context.env_from_host || []).join(", ") || "无"}；git excludes ${c.execution_context.git_excludes_configured ? "已配置" : "未配置"}${c.execution_context.git_isolated ? "、git 已隔离" : ""}（只显示名称）` }),
      h("dt", { text: "能否判定有效性" }), h("dd", { text: r.can_determine_validity ? "可以（只读比较）" : `不能：${[...r.undetermined_aspects.map((a) => ASPECT[a] || a), ...r.workspace_problems].join("；")}` }),
    );
    $("ctx").replaceChildren(h("details", { class: "card ctx" },
      h("summary", { text: o.current ? "证据有效性与检查上下文" : "证据有效性与检查上下文：当前没有可确认为有效的证据，点开查看原因" }),
      body, h("p", { text: r.note })));
  }

  function openUnit(kind, node, step) {
    renderDrawer(kind, node, step);
  }

  function renderFlow(d) {
    const root = $("flow");
    const steps = d.flow.map((st, i) => ({ st, i }));
    const rows = [];
    for (const { st, i } of steps) {
      const risky = st.unit.automation !== "passed" || st.branches.some((b) => b.unit.automation !== "passed");
      if (state.opts.risk && !risky) continue;
      const open = state.opts.all || state.opts.risk || state.expanded.has(st.qid);
      const visible = st.branches.filter((b) => !state.opts.risk || b.unit.automation !== "passed");
      const bs = st.branch_summary;
      const stState = st.unit.automation === "passed" ? "ok" : (st.unit.automation === "failed" || st.unit.automation === "error") ? "bad"
        : outdated(st.unit) || st.unit.automation === "blocked" ? "warn" : "idle";
      const card = h("button", { type: "button", class: "card stepcard", "data-state": stState, onclick: () => openUnit("step", st, st) },
        h("span", { class: "num", text: String(i + 1) }),
        h("h3", {}, st.action, h("span", { class: "sid", text: st.id })),
        st.expected.length ? h("ul", { class: "exp" }, st.expected.map((e) => h("li", { text: e }))) : null,
        dimBadges(st.unit), evidenceLine(st.unit));
      const bar = st.branches.length ? h("div", { class: "branchbar" },
        h("button", {
          type: "button", class: "plus", "aria-expanded": open ? "true" : "false",
          title: "展开/收起边界、异常与恢复分支。收起不会改变右侧的统计。",
          onclick: () => { if (state.expanded.has(st.qid)) state.expanded.delete(st.qid); else state.expanded.add(st.qid); renderFlow(d); },
        }, `${open ? "−" : "+"} ${st.branches.length} 个分支`),
        branchChips(bs)) : null;
      const list = st.branches.length && open ? h("div", { class: "branches" }, visible.map((b) => h("button", {
        type: "button", class: "card branch", onclick: () => openUnit("branch", b, st) },
        h("div", { class: "kind", text: KIND[b.kind] || b.kind }),
        h("div", { class: "cond" }, b.condition, h("span", { class: "sid", text: b.id })),
        b.expected.length ? h("ul", { class: "exp" }, b.expected.map((e) => h("li", { text: e }))) : null,
        h("div", { class: "cont " + b.continuation.type },
          b.continuation.type === "rejoin"
            ? `↩ 处理后汇合到第 ${d.flow.findIndex((x) => x.id === b.continuation.target) + 1} 步「${b.continuation.target_action || b.continuation.target}」`
            : "■ 本次操作到此结束"),
        dimBadges(b.unit), evidenceLine(b.unit)))) : null;
      rows.push(h("div", { class: "step" }, card, bar, list));
    }
    root.replaceChildren(...(rows.length ? rows : [h("div", { class: "empty", text: "没有需要关注的场景。" })]));
  }

  // ---------------------------------------------------------------- 详情抽屉
  function aspectChips(e) {
    if (!e.aspects) return null;
    return h("div", { class: "aspects" }, Object.entries(e.aspects).map(([k, v]) =>
      h("span", { class: "chip " + (v === "same" ? "ok" : v === "changed" ? "warn" : ""), text: `${ASPECT[k] || k}：${ASPECT_STATE[v]}` })));
  }
  function renderEntry(e, d) {
    const box = h("div", { class: "evidence" });
    const v = e.corrupt ? "证据记录损坏或不一致" : (VALIDITY[e.validity] || "—");
    box.append(
      h("div", {}, h("strong", { text: `映射条目 ${e.entry}` }), h("span", { class: "sid", text: ` ${e.entry}` })),
      h("dl", { class: "kv" },
        h("dt", { text: "验证层级" }), h("dd", { title: LEVEL_NOTE, text: `${levelText(e)}（映射声明）· runner：${e.runner || "—"}` }),
        h("dt", { text: "最近结果" }), h("dd", { text: e.has_evidence ? (RESULT[e.last_result] || "—") : "从未执行" }),
        h("dt", { text: "对当前上下文" }), h("dd", { text: v }),
        e.state ? [h("dt", { text: "尝试状态" }), h("dd", { text: `${e.state}${e.reason ? "：" + e.reason : ""}` })] : null,
        e.started_at ? [h("dt", { text: "执行时间" }), h("dd", { text: `${fmtTime(e.started_at)} → ${fmtTime(e.finished_at)}` })] : null,
        e.state ? [h("dt", { text: "整条命令" }), h("dd", { text: `退出码 ${e.exit_code}，${e.command_clean ? "干净" : "存在失败或未完成"}` })] : null,
        e.run_id ? [h("dt", { text: "run" }), h("dd", { class: "mono", text: e.run_id })] : null),
      aspectChips(e));
    if (!e.aspects && e.validity_reasons && e.validity_reasons.length) {  // 有分维度信息时不再重复英文原因
      box.append(h("ul", { class: "exp" }, e.validity_reasons.map((r) => h("li", { text: r }))));
    }
    if (e.changed_env_count) {
      box.append(h("div", { class: "exp", text: `不同的环境变量（共 ${e.changed_env_count} 个，仅名称）：${e.changed_env_names.join(", ")}${e.changed_env_count > e.changed_env_names.length ? " …" : ""}` }));
    }
    box.append(h("div", { class: "exp", text: LEVEL_NOTE }));
    if (e.tests) {
      box.append(h("ul", { class: "tests" }, e.tests.map((t) => h("li", {},
        h("span", { class: "chip " + (t.outcome === "passed" ? "ok" : t.outcome === "failed" ? "bad" : ""), text: RESULT[t.outcome] || t.outcome || "—" }),
        h("span", { class: "mono", text: t.nodeid })))));
      const un = Object.keys(e.unmapped_nonpass || {});
      if (un.length) box.append(h("div", { class: "exp", style: "color:var(--bad)", text: `同一命令中未被映射、但已失败的测试：${un.join(", ")}` }));
    }
    if (e.ref) {
      const slot = h("div", {});
      box.append(h("button", { type: "button", class: "btn", onclick: () => loadAttempt(e.ref, slot) }, "查看运行详情与报告"), slot);
      if (new URLSearchParams(location.search).get("run") === "1") loadAttempt(e.ref, slot);  // 深链: ?open=<场景>&run=1 直接展开运行详情
    }
    return box;
  }
  async function loadAttempt(ref, slot) {
    slot.replaceChildren(h("div", { class: "exp", text: "读取中…" }));
    try {
      const base = `/api/workspaces/${encodeURIComponent(state.ws)}/attempts/${encodeURIComponent(ref.run)}/${encodeURIComponent(ref.story)}/${encodeURIComponent(ref.entry)}`;
      const a = await api(base);
      if (!a.manifest_readable) { slot.replaceChildren(h("div", { class: "exp", text: "manifest 不可读：" + a.integrity_problems.join("；") })); return; }
      const cmd = a.command || {}, rt = a.runtime || {}, b = a.baseline || {};
      const pre = h("pre", { class: "art", hidden: true });
      slot.replaceChildren(
        h("dl", { class: "kv" },
          h("dt", { text: "运行器" }), h("dd", { text: `${a.runner || "pytest"}${a.evidence_kind ? " · " + a.evidence_kind : ""}` }),
          h("dt", { text: "命令" }), h("dd", { class: "mono", text: (cmd.full_argv || cmd.argv || []).join(" ") }),
          h("dt", { text: "工作目录" }), h("dd", { class: "mono", text: cmd.cwd || "—" }),
          a.runner === "flutter" && a.flutter
            ? [h("dt", { text: "事件协议" }), h("dd", { text: `${a.flutter.protocol_version} · 真实测试 ${a.flutter.real_test_count ?? "—"} · 会话 done.success=${a.flutter.done_success} · 隐藏事件 ${(a.flutter.hidden_events || []).length}` }),
               h("dt", { text: "测试文件" }), h("dd", { class: "mono", text: (a.flutter.suites || []).join("、") || "—" })]
            : [h("dt", { text: "pytest rootdir" }), h("dd", { class: "mono", text: a.pytest_rootdir || "—" }),
               h("dt", { text: "收集/剔除" }), h("dd", { text: `${a.collected_count ?? "—"} / ${a.deselected_count ?? "—"}` })],
          h("dt", { text: "分类计数" }), h("dd", { text: JSON.stringify(a.counts || {}) }),
          h("dt", { text: "运行时" }), h("dd", { text: a.runner === "flutter"
            ? `${rt.flutter_path || "—"} · Flutter ${rt.flutter_version || "—"} · Dart ${rt.dart_version || "—"} · 引擎 ${short(rt.engine_revision, 10)} · 包 ${rt.package_count ?? "—"} 个（缓存源码未做内容校验）`
            : `${rt.executable || "—"} · Python ${(rt.python_version || "").split(" ")[0]} · pytest ${rt.pytest_version || "—"} · 依赖 ${a.runtime_distribution_count} 个` }),
          h("dt", { text: "基线" }), h("dd", { class: "mono", text: `故事 ${short(b.story_digest)} · 条目 ${short(b.entry_digest)} · 代码 ${short(b.worktree_fingerprint)} · 运行时 ${short(b.runtime_digest)} · 环境 ${short(b.env_digest)}` }),
          h("dt", { text: "验证器" }), h("dd", { class: "mono", text: b.verifier || "—" }),
          h("dt", { text: "执行期间变化" }), h("dd", { text: a.changed_during_run && a.changed_during_run.length ? a.changed_during_run.join("、") : "无" }),
          h("dt", { text: "完整性" }), h("dd", { text: a.integrity_problems.length ? a.integrity_problems.join("；") : "manifest 与索引一致，产物哈希已核对" })),
        h("div", {}, a.artifacts.map((x) => h("button", {
          type: "button", class: "btn", title: `sha256 ${x.sha256}`,
          onclick: async () => {
            pre.hidden = false; pre.textContent = "读取中…";
            try {
              const r = await api(`${base}/artifacts/${encodeURIComponent(x.name)}`);
              pre.textContent = `# ${x.name}  sha256:${short(r.sha256, 16)}  ${r.size} bytes${r.truncated ? "（已截断）" : ""}\n` + r.text;
            } catch (err) { pre.textContent = String(err.message || err); }
          } }, `${x.name} (${x.size ?? "?"}B)`))),
        pre);
    } catch (err) { slot.replaceChildren(h("div", { class: "exp", text: String(err.message || err) })); }
  }

  function renderDrawer(kind, node, step) {
    const d = state.detail, u = node.unit;
    const a = autoBadge(u);
    const body = $("drawerBody");
    const qs = u.blocked_by.map((id) => d.story.open_questions.find((q) => q.id === id)).filter(Boolean);
    fill(body,
      h("h2", {}, kind === "step" ? node.action : node.condition, h("span", { class: "sid", text: " " + node.id })),
      h("div", { class: "exp", text: kind === "step" ? `主流程第 ${d.flow.findIndex((x) => x.id === node.id) + 1} 步` : `${KIND[node.kind] || node.kind}分支，位于第 ${d.flow.findIndex((x) => x.id === step.id) + 1} 步` }),
      node.expected.length ? h("ul", { class: "exp" }, node.expected.map((e) => h("li", { text: e }))) : null,
      kind === "branch" ? h("div", { class: "cont " + node.continuation.type, text: node.continuation.type === "rejoin" ? `↩ 汇合到「${node.continuation.target_action || node.continuation.target}」` : "■ 本次操作到此结束" }) : null,
      h("h4", { text: "四个维度（互相独立，不合并）" }),
      dimBadges(u),
      h("dl", { class: "kv", style: "margin-top:8px" },
        h("dt", { text: "稳定 ID" }), h("dd", { class: "mono", text: u.qid }),
        h("dt", { text: "自动验证" }), h("dd", { text: `${a.t}${a.tip ? "：" + a.tip : ""}` })),
      qs.length ? [h("h4", { text: "阻塞该场景的待确认问题" }), h("ul", { class: "exp" }, qs.map((q) => h("li", { text: `${q.text}${q.legacy ? "（旧格式，保守阻塞整个故事）" : ""}` })))] : null,
      h("h4", { text: "测试证据" }),
      u.entries.length ? u.entries.map((e) => renderEntry(e, d))
        : h("div", { class: "exp", text: "尚未映射到任何测试。这表示 FlowTree 还没接入，不表示项目缺少对应测试，也不是业务缺陷；需要先核对已有测试再决定是否映射。" }));
    $("drawer").hidden = false;
  }

  // ---------------------------------------------------------------- 数据流
  async function loadStory(refresh) {
    if (!state.story) { $("storyHead").replaceChildren(); $("ctx").replaceChildren(); $("flow").replaceChildren(h("div", { class: "empty", text: "没有故事。请检查工作区配置。" })); return; }
    notice("");
    try {
      const d = await api(`/api/workspaces/${encodeURIComponent(state.ws)}/stories/${encodeURIComponent(state.story)}${refresh ? "?refresh=true" : ""}`);
      state.detail = d;
      renderHead(d); renderContext(d); renderFlow(d);
    } catch (err) { notice("读取故事失败：" + (err.message || err)); }
  }
  async function loadStories(refresh) {
    try {
      const l = await api(`/api/workspaces/${encodeURIComponent(state.ws)}/stories${refresh ? "?refresh=true" : ""}`);
      state.stories = l.stories;
      if (!state.stories.find((s) => s.id === state.story)) state.story = state.stories[0] ? state.stories[0].id : null;
      renderTabs();
    } catch (err) { notice("读取故事列表失败：" + (err.message || err)); }
  }
  async function selectStory(id) {
    state.story = id; state.expanded.clear(); $("drawer").hidden = true;
    history.replaceState(null, "", `#/${encodeURIComponent(state.ws)}/${encodeURIComponent(id)}`);
    renderTabs(); await loadStory(false);
  }
  async function selectWorkspace(id) {
    state.ws = id; state.story = null;
    await loadStories(false);
    if (state.story) history.replaceState(null, "", `#/${encodeURIComponent(state.ws)}/${encodeURIComponent(state.story)}`);
    await loadStory(false);
  }
  async function refresh() {
    $("btnRefresh").disabled = true; $("btnRefresh").textContent = "读取中…";
    try { await loadStories(true); await loadStory(true); } finally { $("btnRefresh").disabled = false; $("btnRefresh").textContent = "重新读取"; }
  }

  function bindOpts() {
    const map = { optIds: "ids", optAll: "all", optRisk: "risk" };
    const q = new URLSearchParams(location.search);  // 深链参数优先于本地记忆: ?ids=1&all=1&risk=1&open=<场景ID>
    for (const [id, key] of Object.entries(map)) {
      const el = $(id);
      state.opts[key] = q.has(key) ? q.get(key) === "1" : load("opt." + key) === "1"; el.checked = state.opts[key];
      el.addEventListener("change", () => { state.opts[key] = el.checked; store("opt." + key, el.checked ? "1" : "0"); apply(); });
    }
    apply();
  }
  function apply() {
    document.body.classList.toggle("show-ids", state.opts.ids);
    if (state.detail) renderFlow(state.detail);
  }

  async function init() {
    bindOpts();
    $("btnRefresh").addEventListener("click", refresh);
    $("drawerClose").addEventListener("click", () => { $("drawer").hidden = true; });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("drawer").hidden = true; });
    try {
      state.workspaces = (await api("/api/workspaces")).workspaces;
    } catch (err) { notice("无法读取工作区：" + (err.message || err)); return; }
    const sel = $("ws");
    sel.replaceChildren(...state.workspaces.map((w) => h("option", { value: w.id, text: `${w.name}（${w.stories} 条故事）` })));
    sel.addEventListener("change", () => selectWorkspace(sel.value));
    if (!state.workspaces.length) { notice("还没有配置工作区。参考 config/workspaces.example.yaml 创建 .flowtree/workspaces.yaml。"); return; }
    const [, wsHash, storyHash] = (location.hash || "").split("/").map(decodeURIComponent);
    const w = state.workspaces.find((x) => x.id === wsHash) || state.workspaces[0];
    sel.value = w.id; state.ws = w.id; state.story = storyHash || null;
    const probs = w.problems.concat(w.config_issues.map((i) => `${i.where}: ${i.message}`));
    if (probs.length) notice("工作区配置问题：" + probs.join("；"));
    await loadStories(false); await loadStory(false);
    const open = new URLSearchParams(location.search).get("open");
    if (open && state.detail) {
      for (const st of state.detail.flow) {
        if (st.qid === open || st.id === open) { openUnit("step", st, st); break; }
        const b = st.branches.find((x) => x.qid === open || x.id === open);
        if (b) { state.expanded.add(st.qid); renderFlow(state.detail); openUnit("branch", b, st); break; }
      }
    }
  }
  init();
})();
