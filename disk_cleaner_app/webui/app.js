/* DiskCleaner Pro — интерфейс на WebView2.
   Разметка строится здесь, данные приходят из Python через pywebview.api. */

const $ = (sel, root = document) => root.querySelector(sel);
const api = () => window.pywebview.api;

const NAV = [
  ["home", "E80F", "Главная"],
  ["clean", "E74D", "Очистка"],
  ["deep", "E90F", "Глубокая очистка"],
  ["analyzer", "E721", "Анализ"],
  ["disks", "EDA2", "Диски"],
  ["duplicates", "E8B7", "Дубликаты"],
  ["history", "E81C", "История"],
  ["startup", "E945", "Автозагрузка"],
  ["uninstaller", "E71D", "Программы"],
];

const LAYER_COLOR = {
  A: "var(--l-a)", B: "var(--l-b)", C: "var(--l-c)", D: "var(--l-d)", E: "var(--l-e)",
};

const VIEWS = {
  home: {
    el: "viewHome",
    title: "Главная",
    sub: "Состояние системы и быстрые действия",
  },
  deep: {
    el: "viewDeep",
    title: "Глубокая очистка",
    sub: "Каждый слой — отдельный уровень риска. Сначала анализ, потом очистка.",
  },
};

let current = "home";
let home = null;

const state = {
  targets: [],
  layers: [],
  summary: { selected: 0, selected_text: "0 Б", found_text: "0 Б", scanned: 0, total: 0 },
  busy: "",
  admin: true,
  filter: null,
  search: "",
  collapsed: new Set(),
  plan: null,
};

const glyph = (code, cls = "glyph") => `<span class="${cls}">&#x${code};</span>`;
const esc = (text) => String(text ?? "").replace(/[&<>"]/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]
));

/* ── статусная строка ─────────────────────────────── */

function status(text, kind = "") {
  $("#statusText").textContent = text;
  const bar = $(".statusbar");
  bar.classList.toggle("busy", kind === "busy");
  bar.classList.toggle("err", kind === "err");
}

/* ── навигация ────────────────────────────────────── */

function renderNav() {
  $("#railList").innerHTML = NAV.map(([id, icon, label]) => `
    <div class="rail-item${id === current ? " active" : ""}" data-view="${id}" tabindex="0">
      ${glyph(icon)}<span class="rail-label">${label}</span>
    </div>`).join("");
}

function navLabel(id) {
  const found = NAV.find((item) => item[0] === id);
  return found ? found[2] : "";
}

function showView(id) {
  current = id;
  for (const view of Object.values(VIEWS)) $("#" + view.el).hidden = true;
  $("#viewSoon").hidden = !!VIEWS[id];
  if (VIEWS[id]) {
    $("#" + VIEWS[id].el).hidden = false;
    $("#pageTitle").textContent = VIEWS[id].title;
    $("#pageSub").textContent = VIEWS[id].sub;
  } else {
    $("#pageTitle").textContent = navLabel(id) || "Раздел";
    $("#pageSub").textContent = "Экран ещё не перенесён на новый интерфейс";
    $("#soonTitle").textContent = `«${navLabel(id)}» пока в Tk-версии`;
  }
  for (const item of document.querySelectorAll(".rail-item")) {
    item.classList.toggle("active", item.dataset.view === id);
  }
  if (id === "home") loadHome();
}

/* ── главная ──────────────────────────────────────── */

const RING_LENGTH = 2 * Math.PI * 52;

function trendChart(points) {
  if (points.length < 2) {
    return `<div class="trend-empty">Точки появляются после очисток и запусков — нужно хотя бы две.</div>`;
  }
  const width = 600;
  const height = 100;
  const pad = 6;
  const values = points.map((p) => p.free);
  const min = Math.min(...values);
  const span = Math.max(1, Math.max(...values) - min);
  const step = width / (points.length - 1);
  const coords = values.map((value, index) => [
    index * step,
    height - pad - ((value - min) / span) * (height - 2 * pad),
  ]);
  const line = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `0,${height} ${line} ${width},${height}`;
  return `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
      <polygon class="area" points="${area}"></polygon>
      <polyline class="line" points="${line}"></polyline>
    </svg>`;
}

function renderHome(data) {
  if (!data) return;
  home = data;

  const hasDisk = data.total > 0;
  $("#homeFree").textContent = data.free_text;
  $("#homeMeta").textContent = hasDisk
    ? `Занято ${data.used_text} из ${data.total_text} · свободно ${data.percent_free}%`
    : "Нет данных о диске";
  $("#homeBar").style.width = `${data.percent_used}%`;
  $("#ringPercent").textContent = hasDisk ? `${data.percent_used}%` : "—";
  $("#ringFill").style.strokeDashoffset =
    String(RING_LENGTH * (1 - (hasDisk ? data.percent_used : 0) / 100));

  $("#homeFreed").textContent = data.freed_text;
  $("#homeCount").textContent = String(data.clean_count);

  const drive = $("#homeDrive");
  drive.innerHTML = data.drives
    .map((name) => `<option${name === data.drive ? " selected" : ""}>${esc(name)}</option>`)
    .join("");

  $("#trendChart").innerHTML = trendChart(data.trend);
  $("#trendMeta").textContent = data.trend.length
    ? `${data.trend[0].label} → ${data.trend[data.trend.length - 1].label} · точек ${data.trend.length}`
    : "нет данных";
  $("#trendForecast").textContent = data.forecast;

  $("#homeBanner").hidden = !data.threshold.visible;
  $("#homeBannerText").textContent = data.threshold.text;

  const top = $("#homeTop");
  if (!data.top.length) {
    top.innerHTML = `
      <div class="empty">
        <div class="empty-title">Пока нет данных</div>
        <div class="empty-sub">Запустите анализ — здесь появятся самые крупные цели.</div>
      </div>`;
    return;
  }
  top.innerHTML = data.top.map((target) => `
    <div class="row" data-top="${esc(target.id)}" title="${esc(target.name)}">
      <span class="row-main"><span class="row-name">${esc(target.name)}</span></span>
      <span class="row-size">${esc(target.size_text)}</span>
    </div>`).join("");
}

async function loadHome() {
  try {
    renderHome(await api().home_state());
  } catch (error) {
    status("Не удалось прочитать состояние диска: " + error, "err");
  }
}

async function pickDrive(drive) {
  renderHome(await api().home_drive(drive));
  status(`Диск ${drive}`);
}

/* ── слои ─────────────────────────────────────────── */

function renderLayers() {
  const box = $("#layers");
  box.innerHTML = state.layers.map((layer) => {
    const color = LAYER_COLOR[layer.id] || "var(--text-3)";
    const all = layer.count > 0 && layer.selected === layer.count;
    const some = layer.selected > 0 && !all;
    const size = layer.size ? bytes(layer.size) : (layer.scanned ? "0 Б" : "—");
    return `
      <div class="layer${all ? " on" : ""}${layer.reclaimable ? "" : " show-only"}${state.filter === layer.id ? " filter" : ""}"
           style="--layer-color:${color}" data-layer="${layer.id}" tabindex="0"
           title="${esc(layer.title)} — ${esc(layer.hint)}">
        <div class="layer-top">
          <span class="layer-badge">${layer.id}</span>
          <span class="layer-title">${esc(layer.title)}</span>
        </div>
        <div class="layer-hint">${esc(layer.hint)}</div>
        <div class="layer-foot">
          <span class="layer-size">${size}</span>
          <span class="layer-count">${layer.selected ? `${layer.selected} из ${layer.count}` : `${layer.count} цел.`}</span>
        </div>
        <span class="layer-check${all ? " on" : some ? " partial" : ""}" data-check="${layer.id}">
          ${all ? glyph("E73E") : ""}
        </span>
      </div>`;
  }).join("");
}

function renderMix() {
  const parts = state.layers.filter((l) => l.size > 0);
  const total = parts.reduce((sum, l) => sum + l.size, 0);
  $("#mixbar").hidden = total <= 0;
  if (total <= 0) return;
  $("#mixTotal").textContent = `всего ${bytes(total)}`;
  $("#mixTrack").innerHTML = parts.map((l) => `
    <span style="width:${(l.size / total * 100).toFixed(2)}%;background:${LAYER_COLOR[l.id]}"
          title="${esc(l.title)} — ${bytes(l.size)}"></span>`).join("");
  $("#mixLegend").innerHTML = parts.map((l) => `
    <span class="legend-item">
      <span class="legend-dot" style="background:${LAYER_COLOR[l.id]}"></span>
      ${l.id} · ${esc(l.title)} — ${bytes(l.size)}
    </span>`).join("");
}

/* ── список целей ─────────────────────────────────── */

function matches(target) {
  if (state.filter && target.layer !== state.filter) return false;
  if (!state.search) return true;
  const needle = state.search.toLowerCase();
  return (target.name + " " + target.description).toLowerCase().includes(needle);
}

function renderTargets() {
  const groups = new Map();
  for (const target of state.targets) {
    if (!matches(target)) continue;
    if (!groups.has(target.layer)) groups.set(target.layer, []);
    groups.get(target.layer).push(target);
  }

  $("#empty").hidden = groups.size > 0;
  if (!groups.size) {
    const empty = $("#empty");
    empty.hidden = false;
    $(".empty-title", empty).textContent = state.search || state.filter
      ? "Ничего не подходит под фильтр"
      : "Пока ничего не найдено";
    $(".empty-sub", empty).textContent = state.search || state.filter
      ? "Измените запрос или снимите фильтр слоя."
      : "Нажмите «Анализировать» — приложение посчитает, сколько можно освободить.";
  }

  const html = [...groups.entries()].map(([layerId, items]) => {
    const layer = state.layers.find((l) => l.id === layerId) || {};
    const selected = items.filter((t) => t.selected).length;
    const size = items.reduce((sum, t) => sum + (t.scanned ? t.size : 0), 0);
    const collapsed = state.collapsed.has(layerId);
    return `
      <div class="group${collapsed ? " collapsed" : ""}" data-group="${layerId}">
        <div class="group-head" data-toggle="${layerId}">
          ${glyph("E70D", "chev")}
          <span class="g-title">${layerId} · ${esc(layer.title || layerId)}</span>
          <span class="g-meta">${selected ? `выбрано ${selected} · ` : ""}${items.length} цел.</span>
          <span class="g-size">${size ? bytes(size) : ""}</span>
        </div>
        <div class="group-body">
          ${items.map(row).join("")}
        </div>
      </div>`;
  }).join("");

  $("#groups").innerHTML = html;
}

function row(target) {
  const tags = [];
  if (target.error) tags.push(`<span class="tag err">недоступно</span>`);
  if (target.admin) tags.push(`<span class="tag warn">нужны права</span>`);
  if (!target.scanned && !target.error) tags.push(`<span class="tag">не проанализировано</span>`);
  const size = target.scanned ? bytes(target.size) : "—";
  return `
    <div class="row${target.selected ? " on" : ""}${target.error ? " blocked" : ""}" data-id="${esc(target.id)}">
      <span class="row-check" data-toggle-row="${esc(target.id)}">${glyph("E73E")}</span>
      <span class="row-main">
        <span class="row-name">${esc(target.name)}</span>
        <span class="row-desc${target.error ? " err" : ""}">${esc(target.error || target.description)}</span>
      </span>
      <span class="row-tags">${tags.join("")}</span>
      <span class="row-size${target.scanned ? "" : " pending"}">${size}</span>
    </div>`;
}

/* ── сводка и нижняя панель ───────────────────────── */

function renderSummary() {
  const s = state.summary;
  const chosen = s.selected > 0;
  $("#btnPlan").disabled = !chosen || !!state.busy;
  $("#btnClean").disabled = !chosen || !!state.busy;

  $("#abSum").textContent = chosen
    ? `Выбрано ${s.selected} · ${s.selected_text}`
    : "Ничего не выбрано";
  $("#abHint").textContent = chosen
    ? "Проверьте план перед удалением"
    : "Отметьте цели или возьмите безопасный набор";

  const chip = $("#chipFound");
  chip.textContent = s.scanned
    ? `найдено ${s.found_text} · целей ${s.scanned} из ${s.total}`
    : `не проанализировано · целей ${s.total}`;
  chip.classList.toggle("muted-chip", !s.scanned);

  $("#pillAdmin").hidden = state.admin;
  $("#statusMeta").textContent = `${s.total} целей · ${s.scanned} проанализировано`
    + (s.errors ? ` · ошибок ${s.errors}` : "");
}

function render() {
  renderLayers();
  renderMix();
  renderTargets();
  renderSummary();
}

/* ── вызовы Python ────────────────────────────────── */

async function applyPayload(payload) {
  if (!payload) return;
  if (payload.targets) state.targets = payload.targets;
  if (payload.layers) state.layers = payload.layers;
  if (payload.summary) state.summary = payload.summary;
  if (typeof payload.to_recycle === "boolean") $("#optRecycle").checked = payload.to_recycle;
  if (typeof payload.admin === "boolean") state.admin = payload.admin;
  if (typeof payload.busy === "string") state.busy = payload.busy;
  render();
}

async function toggleTarget(id, value) {
  const payload = await api().toggle(id, value);
  if (!payload) return;
  const target = state.targets.find((t) => t.id === id);
  if (target) target.selected = value;
  state.layers = payload.layers || state.layers;
  state.summary = payload.summary || state.summary;
  render();
}

async function toggleLayer(layerId, value) {
  await applyPayload(await api().select_layer(layerId, value));
}

/* ── модальные окна ───────────────────────────────── */

let modalCloser = null;

function openModal({ title, body, buttons, wide = false }) {
  closeModal();
  const root = $("#modalRoot");
  const scrim = document.createElement("div");
  scrim.className = "scrim";
  const modal = document.createElement("div");
  modal.className = "modal";
  if (wide) modal.style.width = "min(680px, calc(100vw - 96px))";
  modal.innerHTML = `
    <div class="modal-head">${esc(title)}</div>
    <div class="modal-body">${body}</div>
    <div class="modal-foot"></div>`;
  const foot = $(".modal-foot", modal);
  for (const button of buttons) {
    const el = document.createElement("button");
    el.className = `btn ${button.style || "secondary"}`;
    el.textContent = button.label;
    el.addEventListener("click", () => button.action());
    foot.appendChild(el);
  }
  root.append(scrim, modal);
  requestAnimationFrame(() => { scrim.classList.add("show"); modal.classList.add("show"); });
  modalCloser = () => {
    scrim.classList.remove("show");
    modal.classList.remove("show");
    setTimeout(() => { scrim.remove(); modal.remove(); }, 150);
    modalCloser = null;
  };
}

function closeModal() {
  if (modalCloser) modalCloser();
}

/* ── сценарии ─────────────────────────────────────── */

async function startScan() {
  if (state.busy) return;
  state.collapsed.clear();
  setProgress(null, "Анализ целей…");
  status("Анализ целей…", "busy");
  $("#btnStop").hidden = false;
  await api().scan();
}

function setProgress(ratio, text) {
  const line = $("#progressLine");
  const bar = $("#progressBar");
  if (ratio === null && text === null) {
    line.hidden = true;
    return;
  }
  line.hidden = false;
  line.classList.toggle("indeterminate", ratio === null);
  if (ratio !== null) bar.style.width = `${Math.round(ratio * 100)}%`;
  if (text) status(text, "busy");
}

async function stopScan() {
  await api().stop_scan();
  status("Остановлено", "");
}

function planBody(plan) {
  const lines = [
    `<div class="line"><b>${plan.bytes_text}</b><span>будет освобождено</span></div>`,
    `<div class="line"><span>действий: <b>${plan.actions}</b></span></div>`,
  ];
  if (plan.by_layer.length) {
    lines.push(`<div class="line" style="flex-wrap:wrap;gap:6px">${
      plan.by_layer.map((l) => `<span class="tag">${l.layer} · ${l.text}</span>`).join("")
    }</div>`);
  }
  lines.push(`<div class="note"><b>Что будет удалено</b><ul>${
    plan.targets.filter((t) => !t.blocked).map((t) => (
      `<li>${esc(t.name)} — ${t.text}${t.reclaimable ? "" : " (только показ)"}</li>`
    )).join("")
  }</ul></div>`);
  if (plan.admin_skipped) {
    lines.push(`<div class="note">Без прав администратора будет пропущено целей: ${plan.admin_skipped}.</div>`);
  }
  for (const warning of plan.warnings) {
    lines.push(`<div class="note warn">${esc(warning)}</div>`);
  }
  if ($("#optRecycle").checked) {
    lines.push(`<div class="note warn">Удалённое попадёт в корзину — место освободится после её очистки.</div>`);
  }
  return lines.join("");
}

async function showPlan() {
  $("#btnPlan").disabled = true;
  status("Строим план…", "busy");
  await api().build_plan();
}

async function confirmClean() {
  closeModal();
  $("#btnClean").disabled = true;
  $("#btnPlan").disabled = true;
  setProgress(0, "Очистка…");
  status("Очистка…", "busy");
  await api().clean();
}

/* ── мост из Python ───────────────────────────────── */

window.dc = {
  scanStarted() {
    status("Анализ целей…", "busy");
  },
  progress(done, total) {
    setProgress(total ? done / total : null, `Анализ целей… ${done} из ${total}`);
  },
  async scanDone(payload) {
    await applyPayload(payload);
    setProgress(null, null);
    $("#btnStop").hidden = true;
    const s = state.summary;
    status(
      s.scanned
        ? `Анализ завершён: найдено ${s.found_text}`
        : "Анализ завершён",
      s.errors ? "err" : "",
    );
    if (s.selected === 0 && s.scanned) {
      await applyPayload(await api().safe_set());
      status(`Анализ завершён: найдено ${s.found_text} · выбран безопасный набор`);
    }
    loadHome();
  },
  planStarted() { status("Строим план…", "busy"); },
  planReady(plan) {
    state.plan = plan;
    $("#btnPlan").disabled = false;
    setProgress(null, null);
    status(`План готов: ${plan.bytes_text}, действий ${plan.actions}`);
    openModal({
      title: "План очистки",
      body: planBody(plan),
      wide: true,
      buttons: [
        { label: "Отмена", style: "secondary", action: closeModal },
        {
          label: "Очистить",
          style: "primary",
          action: () => (plan.actions ? confirmClean() : closeModal()),
        },
      ],
    });
  },
  async cleanProgress(done, total, result) {
    setProgress(total ? done / total : null, `Очистка… ${done} из ${total}`);
    const mark = result.status === "OK" ? "✓" : result.status === "ERR" ? "✕" : "•";
    status(`${mark} ${result.name} — ${result.freed_text}`);
  },
  async cleanDone(payload) {
    setProgress(null, null);
    await applyPayload(payload.state);
    loadHome();
    const freed = payload.results.reduce((sum, r) => sum + r.freed, 0);
    status(`Очистка завершена за ${payload.seconds} с · освобождено ${bytes(freed)}`);
    const list = payload.results.map((r) => (
      `<li>${r.status === "OK" ? "✓" : r.status === "ERR" ? "✕" : "•"} ${esc(r.name)} — ${r.freed_text}${
        r.detail ? ` · <span class="muted">${esc(r.detail)}</span>` : ""
      }</li>`
    )).join("");
    openModal({
      title: "Очистка завершена",
      body: `<div class="line"><b>Освобождено ${bytes(freed)}</b><span>за ${payload.seconds} с</span></div>
             <div class="note"><ul>${list}</ul></div>`,
      wide: true,
      buttons: [{ label: "Готово", style: "primary", action: closeModal }],
    });
  },
};

/* ── форматирование ───────────────────────────────── */

const UNITS = ["Б", "КБ", "МБ", "ГБ", "ТБ"];

function bytes(value) {
  let size = Number(value) || 0;
  let index = 0;
  while (size >= 1024 && index < UNITS.length - 1) {
    size /= 1024;
    index += 1;
  }
  const digits = size < 10 && index > 0 ? 1 : 0;
  return `${size.toFixed(digits)} ${UNITS[index]}`;
}

/* ── события ──────────────────────────────────────── */

function bind() {
  document.addEventListener("click", (event) => {
    const check = event.target.closest("[data-toggle-row]");
    if (check) {
      const id = check.dataset.toggleRow;
      const target = state.targets.find((t) => t.id === id);
      if (target) toggleTarget(id, !target.selected);
      return;
    }

    const layerCheck = event.target.closest("[data-check]");
    if (layerCheck) {
      const id = layerCheck.dataset.check;
      const layer = state.layers.find((l) => l.id === id);
      if (layer) toggleLayer(id, layer.selected < layer.count);
      return;
    }

    const layerCard = event.target.closest("[data-layer]");
    if (layerCard) {
      const id = layerCard.dataset.layer;
      state.filter = state.filter === id ? null : id;
      render();
      return;
    }

    const head = event.target.closest("[data-toggle]");
    if (head) {
      const id = head.dataset.toggle;
      if (state.collapsed.has(id)) state.collapsed.delete(id);
      else state.collapsed.add(id);
      renderTargets();
      return;
    }

    const nav = event.target.closest("[data-view]");
    if (nav) {
      showView(nav.dataset.view);
      return;
    }

    const top = event.target.closest("[data-top]");
    if (top) {
      showView("deep");
      toggleTarget(top.dataset.top, true);
      return;
    }

    const cap = event.target.closest("[data-cap]");
    if (cap) {
      const action = cap.dataset.cap;
      if (action === "min") api().win_min();
      if (action === "max") api().win_max().then((max) => document.body.classList.toggle("is-max", !!max));
      if (action === "close") api().win_close();
      return;
    }

    if (event.target.closest("[data-drag]") || event.target.id === "titlebar") {
      api().win_drag();
      return;
    }

    if (event.target.classList.contains("scrim")) closeModal();
  });

  document.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    const grip = event.target.closest("[data-edge]");
    if (grip) {
      event.preventDefault();
      api().win_resize(grip.dataset.edge);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
    if (event.key === "F5" || (event.ctrlKey && event.key === "r")) {
      event.preventDefault();
      startScan();
    }
  });

  $("#search").addEventListener("input", (event) => {
    state.search = event.target.value.trim();
    if (current !== "deep") showView("deep");
    renderTargets();
  });

  $("#homeDrive").addEventListener("change", (event) => pickDrive(event.target.value));
  $("#homeBannerBtn").addEventListener("click", () => showView("deep"));

  $("#btnScan").addEventListener("click", startScan);
  $("#btnStop").addEventListener("click", stopScan);
  $("#btnSafe").addEventListener("click", async () => applyPayload(await api().safe_set()));
  $("#btnNone").addEventListener("click", async () => applyPayload(await api().deselect_all()));
  $("#btnPlan").addEventListener("click", showPlan);
  $("#btnClean").addEventListener("click", showPlan);

  $("#optRecycle").addEventListener("change", async (event) => {
    await api().set_option("to_recycle", event.target.checked);
    status(event.target.checked ? "Удалённое будет перемещено в корзину" : "Удаление без корзины");
  });
}

/* ── старт ────────────────────────────────────────── */

async function boot() {
  renderNav();
  bind();
  // До первого ответа питона страница уже показана: иначе клик по разделу,
  // сделанный за пару секунд загрузки, откатывался бы назад на «Главную».
  showView("home");
  try {
    const data = await api().bootstrap();
    if (data.theme === "light") document.documentElement.dataset.theme = "light";
    await applyPayload(data.state);
    renderHome(data.home);
    $("#optRecycle").checked = !!data.state.to_recycle;
    status("Готов к работе · " + (data.state.admin ? "права администратора" : "без прав администратора"));
  } catch (error) {
    status("Не удалось загрузить движок: " + error, "err");
  }
}

if (window.pywebview) {
  boot();
} else {
  window.addEventListener("pywebviewready", boot, { once: true });
}
