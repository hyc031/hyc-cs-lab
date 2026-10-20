/* Context Pilot 前端逻辑 */
"use strict";

// ---------------- 全局状态 ----------------
let S = null;                 // 后端全量状态
let overflowShown = false;    // 溢出模态框是否已弹出（避免重复弹）
let sectionOpen = { system: true, summary: true, history: true, rag: false, tools: false };
let pendingScroll = true;

// ---------------- 工具 ----------------
const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await resp.json();
  if (data && data.error) throw new Error(data.error);
  return data;
}

function toast(msg, ms = 3200) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), ms);
}

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

function short(text, n = 60) {
  const t = String(text || "").replace(/\s+/g, " ").trim();
  return t.length > n ? t.slice(0, n) + "…" : t;
}

// ---- 轻量 Markdown 渲染（粗体/行内代码/标题/列表/表格） ----
function mdInline(text) {
  return esc(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<i>$2</i>");
}

function mdTable(rows) {
  if (!rows.length) return "";
  const [head, ...body] = rows;
  return `<table class="mdt"><tr>${head.map((c) => `<th>${c}</th>`).join("")}</tr>` +
    body.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("") + "</table>";
}

function md(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const isSep = (l) => /^\s*\|?[\s:|-]+\|?\s*$/.test(l) && l.includes("-");
  let html = "", i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*\|.*\|\s*$/.test(line)) {           // 表格
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        if (!isSep(lines[i])) {
          rows.push(lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => mdInline(c.trim())));
        }
        i++;
      }
      html += mdTable(rows);
      continue;
    }
    if (/^#{1,6}\s/.test(line)) {               // 标题
      html += `<div class="mdh">${mdInline(line.replace(/^#+\s/, ""))}</div>`;
    } else if (/^\s*([-*•]|\d+\.)\s+/.test(line)) {  // 列表项
      html += `<div class="mdli">${mdInline(line.replace(/^\s*([-*•]|\d+\.)\s+/, ""))}</div>`;
    } else if (line.trim() === "") {
      html += `<div class="mdsp"></div>`;
    } else {
      html += `<div>${mdInline(line)}</div>`;
    }
    i++;
  }
  return html;
}

// 涟漪效果
document.addEventListener("mousedown", (e) => {
  const btn = e.target.closest(".md-btn, .strategy-opt, .tab");
  if (!btn) return;
  const rect = btn.getBoundingClientRect();
  const d = Math.max(rect.width, rect.height);
  const span = document.createElement("span");
  span.className = "ripple";
  span.style.width = span.style.height = d + "px";
  span.style.left = (e.clientX - rect.left - d / 2) + "px";
  span.style.top = (e.clientY - rect.top - d / 2) + "px";
  btn.appendChild(span);
  setTimeout(() => span.remove(), 520);
});

// ---------------- 渲染 ----------------
function renderAll() {
  renderMeter();
  renderMode();
  renderDemoBar();
  renderMessages();
  renderContext();
  renderCacheStats();
  renderTrend();
  renderConsole();
  handleOverflow();
}

function renderMeter() {
  const { used, window: win, percent } = S.context;
  $("tokUsed").textContent = used;
  $("tokWindow").textContent = win;
  $("tokPct").textContent = percent + "%";
  $("tokFill").style.width = Math.min(100, percent) + "%";
  const meter = $("meter");
  meter.classList.toggle("warn", percent >= 80 && percent < 95);
  meter.classList.toggle("danger", percent >= 95);
}

function renderMode() {
  document.querySelectorAll("#modeTabs .tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.mode === S.mode);
  });
  const demo = S.mode === "demo";
  $("demoBar").classList.toggle("hidden", !demo);
  const input = $("chatInput");
  input.disabled = demo;
  input.placeholder = demo ? "演示模式：点击上方「下一步」逐步观看" : "输入消息，发送给模型…";
}

function renderDemoBar() {
  if (!S.demo) return;
  const d = S.demo;
  $("demoPhase").textContent = d.phase_title;
  $("demoTitle").textContent = d.title;
  $("demoNarration").textContent = d.narration;
  $("demoStep").textContent = `步骤 ${Math.max(0, d.index) + 1}/${d.total}`;
  $("btnDemoNext").disabled = d.done;
  $("btnDemoNext").textContent = d.done ? "演示完成 ✓" : "下一步 ▸";
}

function renderMessages() {
  const box = $("messages");
  const msgs = S.chat || [];
  if (!msgs.length) {
    box.innerHTML = `<div class="empty-hint">${
      S.mode === "demo"
        ? "点击顶部「下一步」开始演示<br>右侧面板将实时展示 Context 的内部结构"
        : "开始与模型对话吧<br>右侧面板将实时展示 Context 的内部结构"
    }</div>`;
    return;
  }
  box.innerHTML = msgs.map((m) => {
    let badge = "";
    if (m.role === "assistant" && m.cache_tag) {
      badge = m.cache_tag === "hit"
        ? '<span class="cache-badge hit">⚡ CACHE</span>'
        : '<span class="cache-badge miss">🔄 RECALC</span>';
    }
    const meta = `<div class="bubble-meta">${m.tokens} tokens</div>`;
    const body = m.role === "assistant" ? `<div class="bubble md">${badge}${md(m.content)}${meta}</div>`
      : `<div class="bubble">${esc(m.content)}${meta}</div>`;
    return `<div class="msg-row ${esc(m.role)}">${body}</div>`;
  }).join("");
  if (pendingScroll) {
    box.scrollTop = box.scrollHeight;
    pendingScroll = false;
  }
}

function renderContext() {
  const ctx = S.context;
  $("ctxTotal").textContent = `${ctx.used} / ${ctx.window} tokens`;
  const wrap = $("ctxSections");
  wrap.innerHTML = ctx.sections.map((sec) => {
    const open = sectionOpen[sec.key] ? "open" : "";
    const items = sec.items.map((it) => `
      <div class="ctx-item ${it.cached ? "cached" : ""}" data-id="${esc(it.id)}">
        <div class="ctx-item-top">
          <span class="ctx-item-label">${esc(it.label)}</span>
          <span class="ctx-item-tokens">${it.tokens} tok</span>
        </div>
        <div class="ctx-item-preview">${esc(it.preview)}</div>
        <div class="ctx-item-full">${esc(it.content)}</div>
      </div>`).join("");
    return `<div class="ctx-section ${open}" data-key="${esc(sec.key)}">
      <div class="ctx-sec-head" data-sec="${esc(sec.key)}">
        <span>${sec.icon}</span>
        <span class="ctx-sec-title">${esc(sec.title)}${sec.fixed ? "（固定）" : ""}</span>
        <span class="ctx-sec-meta">${sec.tokens} tok · ${sec.percent}%</span>
        <span class="chev">▶</span>
      </div>
      <div class="ctx-sec-bar"><div style="width:${Math.min(100, sec.percent)}%"></div></div>
      <div class="ctx-sec-body">${items || '<div class="ctx-item"><div class="ctx-item-preview">（空）</div></div>'}</div>
    </div>`;
  }).join("");

  // 折叠/展开
  wrap.querySelectorAll(".ctx-sec-head").forEach((head) => {
    head.addEventListener("click", () => {
      const sec = head.closest(".ctx-section");
      const key = sec.dataset.key;
      sectionOpen[key] = !sectionOpen[key];
      sec.classList.toggle("open", sectionOpen[key]);
    });
  });
  // 点击条目展开全文
  wrap.querySelectorAll(".ctx-item").forEach((item) => {
    item.addEventListener("click", () => item.classList.toggle("expanded"));
  });
}

function renderCacheStats() {
  const { hit, miss } = S.stats;
  const lt = S.last_turn;
  $("cacheStats").innerHTML = `
    <div class="cache-line"><span>命中</span><b class="hit-c">⚡ ${hit} 次</b></div>
    <div class="cache-line"><span>未命中</span><b class="miss-c">🔄 ${miss} 次</b></div>
    ${lt ? `<div class="cache-sub">最近一轮：${lt.hit ? "命中，复用 " + lt.reuse_tokens + " tok" : "未命中，重算 " + lt.recalc_tokens + " tok"}</div>` : ""}
  `;
}

function renderTrend() {
  const svg = $("trendSvg");
  const data = S.trend || [];
  const win = S.context.window || 1;
  if (data.length < 2) {
    svg.innerHTML = `<text x="150" y="36" text-anchor="middle" font-size="11" fill="#5B5763">暂无趋势数据（至少两轮对话）</text>`;
    return;
  }
  const W = 300, H = 64, pad = 4;
  const stepX = (W - pad * 2) / (data.length - 1);
  const pts = data.map((v, i) => {
    const x = pad + i * stepX;
    const y = H - pad - Math.min(1, v / win) * (H - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const last = data[data.length - 1] / win;
  const color = last >= 0.95 ? "#D32F2F" : last >= 0.8 ? "#F57C00" : "#6750A4";
  svg.innerHTML = `
    <line x1="0" y1="${(H - pad) / 2}" x2="${W}" y2="${(H - pad) / 2}" stroke="#E7E1EC" stroke-dasharray="3 3"/>
    <polygon points="${pad},${H - pad} ${pts.join(" ")} ${W - pad},${H - pad}" fill="${color}" opacity="0.12"/>
    <polyline points="${pts.join(" ")}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${pts[pts.length - 1].split(",")[0]}" cy="${pts[pts.length - 1].split(",")[1]}" r="3" fill="${color}"/>`;
}

function renderConsole() {
  const pct = S.context.percent;
  const chip = $("usageChip");
  chip.textContent = `当前窗口: ${pct}%`;
  chip.classList.toggle("warn", pct >= 80 && pct < 95);
  chip.classList.toggle("danger", pct >= 95);
}

// ---------------- 溢出模态框 ----------------
function handleOverflow() {
  if (S.context.overflow && !overflowShown) {
    overflowShown = true;
    $("strategyModal").classList.remove("hidden");
  } else if (!S.context.overflow) {
    overflowShown = false;
    $("strategyModal").classList.add("hidden");
  }
}

// ---------------- 详情模态框 ----------------
function showDetails() {
  const d = S.last_strategy;
  const body = $("detailsBody");
  if (!d) {
    body.innerHTML = '<p class="modal-sub">还没有执行过任何策略。当窗口变满时，使用底部控制台的三种策略按钮。</p>';
  } else {
    const names = { delete: "🗑️ 删除历史", summarize: "📝 摘要压缩", trim: "🎯 智能裁剪" };
    const droppedRows = (d.dropped || []).map((x) => `
      <tr>
        <td>${esc(x.label)}</td>
        <td class="mono">${esc(x.preview)}</td>
        <td>${x.tokens}</td>
        <td>${x.score == null ? "—" : x.score}</td>
      </tr>`).join("");
    const keptRows = (d.kept_scores || []).map((x) => `
      <tr>
        <td>${esc(x.label)}</td>
        <td class="mono">${esc(x.preview)}</td>
        <td>—</td>
        <td>${x.score == null ? "—" : x.score}</td>
      </tr>`).join("");
    body.innerHTML = `
      <div class="detail-stats">
        <div class="detail-stat"><div>${d.before_tokens} → ${d.after_tokens} tok</div><b>释放 ${d.freed}</b></div>
        <div class="detail-stat"><div>执行后占用</div><b>${d.percent_after}%</b></div>
        <div class="detail-stat"><div>裁掉条目</div><b>${(d.dropped || []).length}</b></div>
      </div>
      ${d.summary_text ? `<div class="details-summary"><b>摘要引擎：</b>${esc(d.summary_engine || "—")}\n${esc(d.summary_text)}</div>` : ""}
      ${droppedRows ? `<table><tr><th>被处理条目</th><th>内容</th><th>Token</th><th>裁剪得分</th></tr>${droppedRows}</table>` : ""}
      ${keptRows ? `<table style="margin-top:10px"><tr><th>保留条目</th><th>内容</th><th>Token</th><th>裁剪得分</th></tr>${keptRows}</table>` : ""}
      <p class="modal-sub" style="margin-top:12px">策略执行后上下文前缀已改变，下一轮请求将 Cache Miss（🔄 RECALC）。</p>
    `;
    $("detailsTitle").textContent = `${names[d.kind] || d.kind} 执行详情 · ${d.time}`;
  }
  $("detailsModal").classList.remove("hidden");
}

// ---------------- 设置抽屉 ----------------
function openSettings() {
  const c = S.settings;
  $("setLlmUrl").value = c.llm.base_url;
  $("setLlmKey").value = c.llm.api_key;
  $("setLlmModel").value = c.llm.model;
  $("setLlmTemp").value = c.llm.temperature;
  $("setEmbUrl").value = c.embedding.base_url;
  $("setEmbKey").value = c.embedding.api_key;
  $("setEmbModel").value = c.embedding.model;
  $("setMcpEnabled").checked = !!c.mcp.enabled;
  $("setMcpUrl").value = c.mcp.url;
  $("setMcpKey").value = c.mcp.api_key || "";
  $("setRagEnabled").checked = !!c.rag.enabled;
  $("setRagTopK").value = c.rag.top_k;
  $("setWindow").value = c.window;
  updateKbInfo();
  $("settingsDrawer").classList.remove("hidden");
}

function updateKbInfo() {
  const kb = S.kb || {};
  const el = $("kbInfo");
  el.className = "test-result " + (kb.engine && kb.engine !== "none" ? "ok" : "fail");
  el.textContent = kb.engine && kb.engine !== "none"
    ? `${kb.engine} · ${kb.chunks} 分块 · ${kb.docs.length} 文档`
    : "知识库未构建";
}

async function saveSettings() {
  const payload = {
    llm: {
      base_url: $("setLlmUrl").value.trim(),
      api_key: $("setLlmKey").value.trim(),
      model: $("setLlmModel").value.trim(),
      temperature: parseFloat($("setLlmTemp").value) || 0.7,
    },
    embedding: {
      base_url: $("setEmbUrl").value.trim(),
      api_key: $("setEmbKey").value.trim(),
      model: $("setEmbModel").value.trim(),
    },
    mcp: {
      enabled: $("setMcpEnabled").checked,
      url: $("setMcpUrl").value.trim(),
      api_key: $("setMcpKey").value.trim(),
    },
    rag: {
      enabled: $("setRagEnabled").checked,
      top_k: parseInt($("setRagTopK").value) || 3,
    },
    window: parseInt($("setWindow").value) || 2048,
  };
  try {
    const data = await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
    S.settings = data.settings;
    toast("设置已保存");
  } catch (err) {
    toast("保存失败：" + err.message);
  }
}

async function runTest(target, resultEl) {
  const el = $(resultEl);
  el.className = "test-result";
  el.textContent = "测试中…";
  try {
    // 先保存当前表单，保证测试用的是填写中的值
    await saveSettings();
    const r = await api("/api/settings/test", { method: "POST", body: JSON.stringify({ target }) });
    el.className = "test-result " + (r.ok ? "ok" : "fail");
    el.textContent = r.message;
  } catch (err) {
    el.className = "test-result fail";
    el.textContent = err.message;
  }
}

// ---------------- 动作 ----------------
async function refresh() {
  S = await api("/api/state");
  renderAll();
}

function applyState(data) {
  S = data;
  renderAll();
  applyHighlights(data.highlight || []);
  if (data.warnings && data.warnings.length) {
    data.warnings.forEach((w) => toast(w, 5000));
  }
}

function applyHighlights(list) {
  for (const h of list) {
    if (h === "expand-rag") { sectionOpen.rag = true; }
    if (h === "expand-tools") { sectionOpen.tools = true; }
  }
  renderContext();
}

async function sendMessage(e) {
  e.preventDefault();
  if (S.mode === "demo") return;
  const input = $("chatInput");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  $("btnSend").disabled = true;
  $("btnSend").textContent = "思考中…";
  pendingScroll = true;
  try {
    const data = await api("/api/chat", { method: "POST", body: JSON.stringify({ message: text }) });
    applyState(data);
  } catch (err) {
    toast(err.message, 5000);
    await refresh();
  } finally {
    $("btnSend").disabled = false;
    $("btnSend").textContent = "发送";
    input.focus();
  }
}

async function demoNext() {
  try {
    const data = await api("/api/demo/next", { method: "POST", body: "{}" });
    pendingScroll = true;
    applyState(data);
  } catch (err) { toast(err.message); }
}

async function demoReset() {
  const data = await api("/api/demo/reset", { method: "POST", body: "{}" });
  pendingScroll = true;
  applyState(data);
}

async function switchMode(mode) {
  if (mode === S.mode) return;
  if (S.chat.length && !confirm("切换模式将重置当前会话，确定继续？")) return;
  const data = await api("/api/mode", { method: "POST", body: JSON.stringify({ mode }) });
  applyState(data);
}

async function runStrategy(kind) {
  try {
    $("strategyModal").classList.add("hidden");
    const data = await api("/api/strategy", { method: "POST", body: JSON.stringify({ kind }) });
    applyState(data);
    if (kind !== "delete") showDetails();
    else showDetails();
  } catch (err) { toast(err.message); }
}

// ---------------- 事件绑定 ----------------
$("chatForm").addEventListener("submit", sendMessage);
$("btnDemoNext").addEventListener("click", demoNext);
$("btnDemoReset").addEventListener("click", demoReset);
$("btnReset").addEventListener("click", async () => {
  if (!confirm("确定重置当前会话？")) return;
  applyState(await api("/api/reset", { method: "POST", body: "{}" }));
});
document.querySelectorAll("#modeTabs .tab").forEach((tab) => {
  tab.addEventListener("click", () => switchMode(tab.dataset.mode));
});
document.querySelectorAll("[data-strategy]").forEach((btn) => {
  btn.addEventListener("click", () => runStrategy(btn.dataset.strategy));
});
$("btnDismissStrategy").addEventListener("click", () => $("strategyModal").classList.add("hidden"));
$("btnDetails").addEventListener("click", showDetails);
$("btnCloseDetails").addEventListener("click", () => $("detailsModal").classList.add("hidden"));

$("btnSettings").addEventListener("click", openSettings);
$("btnCloseSettings").addEventListener("click", () => $("settingsDrawer").classList.add("hidden"));
$("btnSaveSettings").addEventListener("click", saveSettings);
$("btnTestLlm").addEventListener("click", () => runTest("llm", "testLlmResult"));
$("btnTestEmb").addEventListener("click", () => runTest("embedding", "testEmbResult"));
$("btnTestMcp").addEventListener("click", () => runTest("mcp", "testMcpResult"));
$("btnModels").addEventListener("click", async () => {
  await saveSettings();
  const r = await api("/api/settings/models");
  const list = $("modelList");
  list.innerHTML = (r.models || []).map((m) => `<option value="${esc(m)}">`).join("");
  toast(r.ok ? `已拉取 ${r.models.length} 个模型，可在模型名称输入框中选择` : (r.message || "拉取失败"));
});
$("btnRebuildKb").addEventListener("click", async () => {
  const el = $("kbInfo");
  el.className = "test-result";
  el.textContent = "构建中…";
  try {
    await saveSettings();
    const data = await api("/api/kb/rebuild", { method: "POST", body: "{}" });
    S = data;
    updateKbInfo();
    renderAll();
    toast((S.kb && S.kb.error ? "索引完成（有警告）" : "索引完成"));
  } catch (err) { el.textContent = err.message; }
});

$("btnEditSystem").addEventListener("click", () => {
  $("systemInput").value = S.system_prompt || "";
  $("systemModal").classList.remove("hidden");
});
$("btnCancelSystem").addEventListener("click", () => $("systemModal").classList.add("hidden"));
$("btnSaveSystem").addEventListener("click", async () => {
  const data = await api("/api/system", { method: "POST", body: JSON.stringify({ system_prompt: $("systemInput").value }) });
  $("systemModal").classList.add("hidden");
  applyState(data);
});

// ---------------- 启动 ----------------
refresh().catch((err) => {
  $("messages").innerHTML = `<div class="empty-hint">无法连接后端：${esc(err.message)}<br>请先启动 FastAPI 服务（见 README）</div>`;
});
