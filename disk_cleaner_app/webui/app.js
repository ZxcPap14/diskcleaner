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
  ["dup", "E8B7", "Дубликаты"],
  ["history", "E81C", "История"],
  ["startup", "E945", "Автозагрузка"],
  ["programs", "E71D", "Программы"],
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
  clean: {
    el: "viewClean",
    title: "Очистка",
    sub: "Безопасное сканирование и удаление временных данных",
  },
  history: {
    el: "viewHistory",
    title: "История",
    sub: "Что и когда удалялось",
  },
  programs: {
    el: "viewPrograms",
    title: "Программы",
    sub: "Установленные приложения, их размер и удаление",
  },
  startup: {
    el: "viewStartup",
    title: "Автозагрузка",
    sub: "Что запускается вместе с Windows",
  },
  dup: {
    el: "viewDup",
    title: "Дубликаты",
    sub: "Одинаковые файлы: покажем и удалим лишние копии",
  },
  disks: {
    el: "viewDisks",
    title: "Диски",
    sub: "Занятость томов, прогноз и состояние железа",
  },
  analyzer: {
    el: "viewAnalyzer",
    title: "Анализ",
    sub: "Крупные папки, файлы, расширения и treemap",
  },
  settings: {
    el: "viewSettings",
    title: "Настройки",
    sub: "Тема, правила, история, расписание и обновления",
  },
};

let current = "home";
let home = null;
let hist = null;
let programs = null;
let startup = null;
let startupSearch = "";
let dup = null;
let disks = null;
let ana = null;
let anaMode = "";
let anaTreemapOn = false;
let setst = null;
let setSelRule = "";
let setSelWl = "";
const dupChecked = new Set();
const dupCollapsed = new Set();

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
  mode: "easy",
};

/* SAFETY: простой режим — только рекомендованные и безопасные цели. */
const SAFETY_GROUPS = [
  ["\u{1F7E2}", "Безопасные"],
  ["\u{1F7E1}", "Требуют внимания"],
  ["\u{1F534}", "Опасные"],
];

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
  document.body.dataset.view = id;
  if (id === "home") loadHome();
  if (id === "history") loadHistory();
  if (id === "programs") loadPrograms();
  if (id === "startup") loadStartup();
  if (id === "dup") loadDup();
  if (id === "disks") loadDisks();
  if (id === "analyzer") loadAnalyzer();
  if (id === "settings") loadSettings();
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

/* ── история ──────────────────────────────────────── */

function histChart(points) {
  if (!points.length) {
    return `<div class="trend-empty">Нет данных — журнал пока пуст.</div>`;
  }
  const width = 600;
  const height = 92;
  const pad = 4;
  const max = Math.max(1, ...points.map((p) => p.bytes));
  const step = width / points.length;
  const barW = Math.min(48, Math.max(2, step - 8));
  const bars = points.map((point, index) => {
    const h = ((point.bytes / max) * (height - 24)) || 1;
    const x = index * step + (step - barW) / 2;
    const y = height - pad - h;
    return `<rect class="bar" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" rx="2"><title>${point.day} · ${esc(point.text)}</title></rect>
      <text class="axis" x="${(x + barW / 2).toFixed(1)}" y="${height - 1}" text-anchor="middle">${point.day}</text>`;
  });
  return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">${bars.join("")}</svg>`;
}

function renderHistory() {
  const type = $("#histType").value;
  const all = (hist && hist.entries) || [];
  const entries = type ? all.filter((entry) => entry.type === type) : all;
  $("#histCount").textContent = hist ? hist.count : 0;
  $("#histTotal").textContent = hist ? hist.total_text : "0 Б";
  $("#histChart").innerHTML = histChart(hist ? hist.chart : []);
  $("#histEmpty").hidden = entries.length > 0;
  $("#histChip").textContent = entries.length
    ? `${entries.length} из ${all.length}`
    : "журнал пуст";
  $("#histList").innerHTML = entries.map((entry) => `
    <div class="hist-row" title="${esc(entry.details.map((d) => d.name).join(", "))}">
      <span class="hist-date">${esc(entry.date)}</span>
      <span class="hist-type">${esc(entry.type_label)}</span>
      <span class="hist-items">${entry.items} цел.</span>
      <span class="hist-size">${esc(entry.size_text)}</span>
    </div>`).join("");
}

async function loadHistory() {
  try {
    hist = await api().history_state();
    renderHistory();
  } catch (error) {
    status("Не удалось прочитать историю: " + error, "err");
  }
}

/* ── программы ────────────────────────────────────── */

function progMatches(app) {
  const drive = $("#progDrive").value;
  if (drive && app.drive !== drive) return false;
  const needle = ($("#progSearch").value || "").trim().toLowerCase();
  if (!needle) return true;
  return (app.name + " " + (app.publisher || "")).toLowerCase().includes(needle);
}

function renderPrograms() {
  if (!programs) return;
  const apps = programs.apps.filter(progMatches);
  $("#progCount").textContent = apps.length;
  $("#progChip").textContent = programs.measuring ? "размеры считаются…" : "готово";
  $("#progChip").classList.toggle("muted-chip", !programs.measuring);
  $("#progEmpty").hidden = apps.length > 0;
  $("#progList").innerHTML = apps.map((app) => `
    <div class="prog-row">
      <div class="prog-name">
        <b title="${esc(app.name)}">${esc(app.name)}</b>
        <span>${esc([app.publisher, app.drive].filter(Boolean).join(" · "))}</span>
      </div>
      <span class="prog-cell">${esc(app.version || "—")}</span>
      <span class="prog-cell">${esc(app.date || "—")}</span>
      <span class="prog-size${app.size_text ? "" : " pending"}">${esc(app.size_text || "—")}</span>
      <span class="prog-act">
        <button class="btn icon" title="Удалить программу" data-uninstall="${esc(app.id)}">
          <span class="glyph">&#xE74D;</span>
        </button>
      </span>
    </div>`).join("");
}

async function loadPrograms() {
  try {
    programs = await api().programs_state();
    const select = $("#progDrive");
    select.innerHTML = [`<option value="">Все диски</option>`]
      .concat(programs.drives.map((d) => `<option value="${esc(d)}">${esc(d)}</option>`))
      .join("");
    programs.measuring = true;
    renderPrograms();
    status("Читаю установленные программы…", "busy");
    await api().programs_measure();
    status(`Программ: ${programs.count}`, "");
  } catch (error) {
    status("Не удалось прочитать список программ: " + error, "err");
  }
}

/* ── автозагрузка ─────────────────────────────────── */

function startMatches(item) {
  if (!startupSearch) return true;
  return item.name.toLowerCase().includes(startupSearch.toLowerCase());
}

function renderStartup() {
  if (!startup) return;
  const items = startup.items.filter(startMatches);
  $("#startOn").textContent = startup.enabled;
  $("#startOff").textContent = startup.disabled;
  $("#startChip").textContent = `${startup.count} записей`;
  $("#startEmpty").hidden = items.length > 0;
  $("#startList").innerHTML = items.map((item) => `
    <div class="start-row${item.enabled ? "" : " off"}" data-start="${esc(item.id)}">
      <div class="start-name">
        <b title="${esc(item.name)}">${esc(item.name)}</b>
        <span title="${esc(item.command)}">${esc(item.command)}</span>
      </div>
      <span class="start-src">${esc(item.source)}</span>
      <span>
        <label class="switch">
          <input type="checkbox" data-start-toggle="${esc(item.id)}"${item.enabled ? " checked" : ""} />
          <span class="switch-track"><span class="switch-thumb"></span></span>
        </label>
      </span>
    </div>`).join("");
}

async function loadStartup() {
  try {
    startup = await api().startup_state();
    renderStartup();
    status(`Автозагрузка: ${startup.enabled} включено, ${startup.disabled} отключено`, "");
  } catch (error) {
    status("Не удалось прочитать автозагрузку: " + error, "err");
  }
}

async function toggleStartup(id, enabled) {
  status(enabled ? "Включаю запись…" : "Отключаю запись…", "busy");
  startup = await api().startup_toggle(id, enabled);
  renderStartup();
  status(enabled ? "Запись включена" : "Запись отключена", "");
}

/* ── дубликаты ────────────────────────────────────── */

async function loadDup() {
  dup = await api().dup_state();
  dupChecked.clear();
  renderDup();
}

function renderDup() {
  if (!dup) return;
  const root = $("#dupRoot");
  root.textContent = dup.root;
  root.title = dup.root;

  let marked = 0;
  let wasted = 0;
  for (const group of dup.groups) {
    for (const file of group.files) {
      if (file.original || !dupChecked.has(file.path)) continue;
      marked += 1;
      wasted += group.size;
    }
  }

  $("#dupSum").textContent = marked
    ? `Отмечено ${marked} файлов · ${bytes(wasted)}`
    : "Ничего не отмечено";
  $("#dupDelete").disabled = !marked || !!dup.busy;
  $("#dupStop").disabled = !dup.busy;
  $("#dupScan").disabled = !!dup.busy;
  $("#dupChip").textContent = dup.busy
    ? "идёт поиск…"
    : (dup.count ? `${dup.count} групп · ${dup.wasted_text}` : "ничего не найдено");
  $("#dupEmpty").hidden = dup.count > 0 || dup.busy;

  $("#dupList").innerHTML = dup.groups.map((group) => {
    const collapsed = dupCollapsed.has(group.id);
    const files = group.files.map((file) => {
      const locked = !!file.locked;
      const checked = file.original || (!locked && dupChecked.has(file.path));
      return `
        <label class="dup-file">
          <input type="checkbox" data-dup-file="${esc(file.path)}"${checked ? " checked" : ""}${file.original || locked ? " disabled" : ""} />
          <span class="dup-name">${esc(file.name)}</span>
          <span class="dup-path">${esc(file.dir)}</span>
          ${file.original ? `<span class="dup-tag">оригинал</span>` : ""}
          ${locked ? `<span class="dup-tag" title="Путь защищён белым списком">🔒 белый список</span>` : ""}
        </label>`;
    }).join("");
    return `
      <div class="dup-group${collapsed ? " collapsed" : ""}">
        <div class="dup-head" data-dup-group="${group.id}">
          ${glyph("E70D", "chev")}
          <span class="dup-name">${esc(group.name)}</span>
          <span class="dup-meta">${group.count} файлов · ${group.size_text}${group.locked ? ` · 🔒 ${group.locked}` : ""}</span>
          <span class="dup-wasted">${group.wasted_text}</span>
        </div>
        <div class="dup-files">${files}</div>
      </div>`;
  }).join("");
}

async function dupPick() {
  dup = await api().dup_pick();
  dupChecked.clear();
  renderDup();
}

async function dupScan() {
  if (!dup) return;
  const mode = $("#dupMode .seg-item.on");
  dup.busy = true;
  renderDup();
  status("Ищем дубликаты…", "busy");
  await api().dup_scan(mode ? mode.dataset.mode : "fast");
}

function confirmDupDelete() {
  const paths = [...dupChecked];
  if (!paths.length) return;
  openModal({
    title: "Удалить копии?",
    body: `<div class="note">Будет удалено файлов: <b>${paths.length}</b>. Оригинал в каждой группе остаётся на месте.</div>`,
    buttons: [
      { label: "Отмена", style: "secondary", action: closeModal },
      {
        label: "Удалить",
        style: "danger",
        action: async () => {
          closeModal();
          status("Удаляем копии…", "busy");
          await api().dup_delete(paths, $("#dupRecycle").checked);
        },
      },
    ],
  });
}

/* ── диски ────────────────────────────────────────── */

function renderDisks() {
  const data = disks;
  if (!data) return;
  $("#volCount").textContent = String(data.volumes.length);
  $("#volGrid").innerHTML = data.volumes.map((vol) => {
    const cls = vol.percent_used >= 92 ? "crit" : vol.percent_used >= 80 ? "warn" : "";
    return `
      <div class="vol-card ${cls}">
        <div class="vol-top">
          <span class="vol-name">${esc(vol.name)}</span>
          <span class="vol-free"><b>${vol.free_text}</b> свободно</span>
        </div>
        <div class="vol-bar"><span style="width:${vol.percent_used}%"></span></div>
        <div class="vol-meta">занято ${vol.used_text} из ${vol.total_text} · ${vol.percent_used}%</div>
        ${vol.forecast ? `<div class="vol-forecast">${esc(vol.forecast)}</div>` : ""}
      </div>`;
  }).join("");

  $("#diskEmpty").hidden = data.disks.length > 0 || data.busy;
  $("#diskChip").textContent = data.busy
    ? "читаем SMART…"
    : data.smart_ready ? `${data.disks.length} дисков` : "нет данных";
  $("#diskList").innerHTML = data.disks.map((disk) => `
    <div class="disk-row" title="${esc(disk.summary)}">
      <div class="disk-name">
        <b>${esc(disk.model)}</b>
        <span>${esc([disk.media, disk.bus, disk.hours, disk.wear].filter(Boolean).join(" · "))}</span>
      </div>
      <span class="disk-cell">${disk.size_text}</span>
      <span class="disk-cell">${esc(disk.temperature || "—")}</span>
      <span><span class="disk-badge ${disk.health}">${esc(disk.health_label)}</span></span>
    </div>`).join("");
}

async function loadDisks(force = false) {
  disks = await api().disks_state();
  renderDisks();
  if (force || !disks.smart_ready) await api().disks_smart();
}

/* ── анализ ───────────────────────────────────────── */

function anaChipText(text) {
  $("#anaChip").textContent = text;
}

async function loadAnalyzer() {
  ana = await api().analyzer_state();
  renderAnalyzerShell();
  if (anaMode) anaRun(anaMode, false);
}

function renderAnalyzerShell() {
  const data = ana;
  if (!data) return;
  $("#anaDrive").innerHTML = data.drives
    .map((d) => `<option value="${esc(d.root)}"${d.root === data.drive ? " selected" : ""}>${esc(d.name)}</option>`)
    .join("");
  $("#anaSize").innerHTML = data.size_choices
    .map((c) => `<option value="${c.mb}">${esc(c.label)}</option>`).join("");
  $("#anaAge").innerHTML = data.age_choices
    .map((c) => `<option value="${c.days}">${esc(c.label)}</option>`).join("");
}

async function anaDriveChange(drive) {
  ana = await api().analyzer_set_drive(drive);
  renderAnalyzerShell();
  anaResetResult();
  status(`Диск: ${drive}`);
}

function anaResetResult() {
  $("#anaList").innerHTML = "";
  $("#anaHead").hidden = true;
  $("#anaEmpty").hidden = false;
  $("#anaFileFilters").hidden = true;
  $("#anaExtCard").hidden = true;
  $("#anaTreemapCard").hidden = true;
  $("#anaRemoveEmpty").hidden = true;
}

async function anaRun(mode, force = true) {
  anaMode = mode;
  anaTreemapOn = false;
  anaChipText("анализ…");
  $("#anaStop").hidden = false;
  $("#anaRemoveEmpty").hidden = true;
  if (force) anaResetResult();
  await api().analyzer_run(mode, force);
}

async function anaShowTreemap() {
  anaMode = "";
  anaTreemapOn = true;
  anaChipText("treemap…");
  anaResetResult();
  $("#anaTreemapCard").hidden = false;
  $("#anaCrumb").textContent = ana ? ana.drive : "";
  await api().analyzer_treemap("", false);
}

async function anaApplyFilters() {
  const ext = $("#anaExt").value || "";
  const sizeMb = Number($("#anaSize").value) || 10;
  const ageDays = Number($("#anaAge").value) || 0;
  const report = await api().analyzer_filter(ext, sizeMb, ageDays);
  renderFileRows(report);
}

function renderFileRows(report) {
  $("#anaHead").hidden = false;
  $("#anaHead").innerHTML = [
    '<span class="ana-num">#</span>',
    '<span class="ana-size">Размер</span>',
    "<span>Изменён</span>",
    "<span>Путь</span>",
  ].join("");
  $("#anaEmpty").hidden = report.rows.length > 0;
  $("#anaFilterInfo").textContent = `подходит ${report.matched} · ${report.matched_text}`;
  $("#anaList").innerHTML = report.rows.map((f) => `
    <div class="ana-row ana-file" title="${esc(f.path)}">
      <span class="ana-num">${f.index}</span>
      <span class="ana-size">${esc(f.size_text)}</span>
      <span class="ana-num">${esc(f.modified_text)} · ${esc(f.age_text)}</span>
      <span class="p">${esc(f.path)}</span>
    </div>`).join("");
}

function renderAnalyzerDone(p) {
  anaChipText(
    p.cancelled ? "остановлено"
      : p.cached ? `кэш ${p.when || ""} · «Обновить» для повтора`
        : p.mode === "files" ? `${p.total_files} файлов · ${p.total_text}`
          : p.mode === "empty" ? `пустых папок: ${p.count}`
            : `${(p.rows || []).length} папок`,
  );
  $("#anaStop").hidden = true;
  $("#anaTreemapCard").hidden = true;

  if (p.mode === "files") {
    $("#anaFileFilters").hidden = false;
    $("#anaExtCard").hidden = false;
    renderExtCard(p.extensions || []);
    anaApplyFilters();
    return;
  }

  $("#anaFileFilters").hidden = true;
  $("#anaExtCard").hidden = true;
  const rows = p.rows || [];
  if (p.mode === "top") {
    $("#anaHead").hidden = false;
    $("#anaHead").innerHTML = [
      '<span class="ana-num">#</span>',
      "<span>Папка</span>",
      "<span>Расположение</span>",
      '<span class="ana-size">Размер</span>',
    ].join("");
    $("#anaList").innerHTML = rows.map((r) => `
      <div class="ana-row ana-top" title="${esc(r.path)}">
        <span class="ana-num">${r.index}</span>
        <span><b>${esc(r.name)}</b></span>
        <span class="p">${esc(r.path)}</span>
        <span class="ana-size">${esc(r.size_text)}</span>
      </div>`).join("");
    $("#anaEmpty").hidden = rows.length > 0;
  } else if (p.mode === "empty") {
    $("#anaHead").hidden = false;
    $("#anaHead").innerHTML = [`<span>Пустые папки: ${p.count || 0}${p.hidden ? ` (показаны 200)` : ""}</span>`].join("");
    $("#anaList").innerHTML = rows.map((r) => `
      <div class="ana-row ana-paths" title="${esc(r.path)}">
        <span class="path">${esc(r.path)}</span>
      </div>`).join("");
    $("#anaEmpty").hidden = rows.length > 0;
    $("#anaRemoveEmpty").hidden = !(p.count > 0);
  }
}

function renderExtCard(chips) {
  $("#anaExtChips").innerHTML = chips.length
    ? chips.map((c) => `
      <span class="chip">${esc(c.label)} · ${esc(c.size_text)} · ${c.percent}%</span>`).join("")
    : '<span class="chip muted-chip">нет файлов выше порога</span>';
  const current = $("#anaExt").value;
  $("#anaExt").innerHTML =
    '<option value="">Все расширения</option>' +
    chips.map((c) => `<option value="${esc(c.extension)}">${esc(c.label)} · ${esc(c.size_text)}</option>`).join("");
  if ([...$("#anaExt").options].some((o) => o.value === current)) $("#anaExt").value = current;
}

/* treemap: раскладка squarify в JS */
function tmLayout(nodes, x, y, w, h) {
  const total = nodes.reduce((s, n) => s + n.val, 0) || 1;
  const scale = (w * h) / total;
  const items = nodes.map((n) => ({ ...n, a: n.val * scale })).filter((n) => n.a > 0.5);
  const out = [];
  let idx = 0;
  let X = x, Y = y, W = w, H = h;
  const worst = (row, area, side) => {
    const th = area / side;
    return Math.max(...row.map((it) => {
      const len = it.a / th;
      return Math.max(len / th, th / len);
    }));
  };
  while (idx < items.length) {
    const side = Math.min(W, H);
    const row = [items[idx]];
    let rowArea = row[0].a;
    let best = worst(row, rowArea, side);
    idx++;
    while (idx < items.length) {
      const cand = [...row, items[idx]];
      const wr = worst(cand, rowArea + items[idx].a, side);
      if (wr <= best) { row.push(items[idx]); rowArea += items[idx].a; best = wr; idx++; }
      else break;
    }
    if (W >= H) {
      const th = rowArea / H;
      let cy = Y;
      for (const it of row) {
        const ih = it.a / th;
        out.push({ ...it, x: X, y: cy, w: th, h: ih });
        cy += ih;
      }
      X += th; W -= th;
    } else {
      const th = rowArea / W;
      let cx = X;
      for (const it of row) {
        const iw = it.a / th;
        out.push({ ...it, x: cx, y: Y, w: iw, h: th });
        cx += iw;
      }
      Y += th; H -= th;
    }
  }
  return out;
}

function renderTreemap(p) {
  anaChipText(`${p.nodes.length} элементов`);
  $("#anaBack").disabled = !p.can_back;
  $("#anaCrumb").textContent = p.path;
  const box = $("#anaTreemapBox");
  const W = box.clientWidth || 800;
  const H = box.clientHeight || 420;
  const nodes = p.nodes.map((n) => ({ ...n, val: n.percent }));
  const rects = tmLayout(nodes, 0, 0, W, H);
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  for (const r of rects) {
    const g = document.createElementNS(ns, "g");
    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("x", r.x + 0.5); rect.setAttribute("y", r.y + 0.5);
    rect.setAttribute("width", Math.max(0, r.w - 1.5)); rect.setAttribute("height", Math.max(0, r.h - 1.5));
    rect.setAttribute("rx", 3);
    rect.setAttribute("class", `tm-rect${r.is_dir ? "" : " leaf"}`);
    rect.setAttribute("fill", "var(--accent)");
    rect.setAttribute("fill-opacity", (0.12 + Math.min(0.55, r.percent / 100 * 0.9)).toFixed(2));
    if (r.is_dir) {
      rect.addEventListener("click", () => {
        anaChipText("treemap…");
        api().analyzer_treemap(r.path, false);
      });
      rect.addEventListener("dblclick", () => api().analyzer_open(r.path));
    }
    g.appendChild(rect);
    if (r.w > 52 && r.h > 26) {
      const label = document.createElementNS(ns, "text");
      label.setAttribute("x", r.x + 6); label.setAttribute("y", r.y + 15);
      label.setAttribute("class", "tm-label");
      label.textContent = r.name.length > Math.floor(r.w / 7)
        ? r.name.slice(0, Math.max(1, Math.floor(r.w / 7) - 1)) + "…" : r.name;
      g.appendChild(label);
      if (r.h > 40) {
        const sub = document.createElementNS(ns, "text");
        sub.setAttribute("x", r.x + 6); sub.setAttribute("y", r.y + 28);
        sub.setAttribute("class", "tm-sub");
        sub.textContent = `${r.size_text} · ${r.percent}%`;
        g.appendChild(sub);
      }
    }
    svg.appendChild(g);
  }
  box.innerHTML = "";
  box.appendChild(svg);
}

/* ── настройки ────────────────────────────────────── */

async function loadSettings() {
  setst = await api().settings_state();
  renderSettings();
}

async function exportReport(kind) {
  const result = await settingsGuard(() => api().export_report(kind), "Экспорт не удался");
  if (result && result.ok) status(`Отчёт сохранён: ${result.path}`);
}

function renderSettings() {
  const s = setst;
  if (!s) return;
  $("#setTheme").value = s.theme;
  $("#setRecycle").checked = s.to_recycle;
  $("#setSafe").checked = s.safe_mode;
  $("#setRestore").checked = s.restore_point;
  $("#setThreshold").value = s.threshold;
  $("#setAutostart").checked = s.autostart;
  $("#setUpdateSource").value = s.update_source;
  $("#setMode").value = s.schedule.mode;
  $("#setSchedNote").textContent = s.schedule.exists
    ? `✅ Задание активно: ${s.schedule.mode_text}, раз в неделю.`
    : "Задание не создано.";
  const hist = s.history;
  $("#setHistNote").textContent =
    `Операций: ${hist.count} · освобождено всего: ${hist.total_text}\n` +
    hist.recent.map((r) => `• ${r.when} — ${r.targets} целей, ${r.freed_text}`).join("\n");
  $("#setRules").innerHTML = s.rules.length ? s.rules.map((r) => `
    <div class="rule-row${r.id === setSelRule ? " selected" : ""}" data-rule-id="${esc(r.id)}">
      <span>${esc(r.name)}</span>
      <span>${esc(r.safety_label)}</span>
      <span class="path">${esc(r.path)}</span>
    </div>`).join("")
    : '<div class="hist-note">Правил пока нет.</div>';
  $("#setWhitelist").innerHTML = s.whitelist.length ? s.whitelist.map((p) => `
    <div class="rule-row${p === setSelWl ? " selected" : ""}" data-wl-path="${esc(p)}">
      <span class="path" style="grid-column:1/-1;">${esc(p)}</span>
    </div>`).join("")
    : '<div class="hist-note">Список пуст — эти пути никогда не попадут в план очистки.</div>';
}

async function applySettings(state, note) {
  setst = state;
  if (state.theme) {
    document.documentElement.dataset.theme = state.theme === "light" ? "light" : "dark";
  }
  renderSettings();
  if (note) status(note);
}

async function settingsGuard(fn, failText) {
  try {
    return await fn();
  } catch (error) {
    status(`${failText}: ${error}`, "err");
    return null;
  }
}

function ruleDialog(rule) {
  const editing = !!rule;
  openModal({
    title: editing ? "Изменить правило" : "Новое правило",
    body: `
      <div class="note">Путь будет проверен правилами безопасности перед добавлением.</div>
      <div class="line"><b>Название</b></div>
      <input type="text" class="input" id="dlgRuleName" style="width:100%"
             value="${esc(rule ? rule.name : "")}">
      <div class="line" style="margin-top:10px;"><b>Путь (папка или файл)</b></div>
      <input type="text" class="input" id="dlgRulePath" style="width:100%"
             value="${esc(rule ? rule.path : "")}">
      <div class="line" style="margin-top:10px;"><b>Уровень риска</b></div>
      <select class="select" id="dlgRuleSafety">
        <option value="🟢">Безопасно</option>
        <option value="🟡" selected>Осторожно</option>
        <option value="🔴">Продвинутый</option>
      </select>`,
    wide: true,
    buttons: [
      { label: "Отмена", style: "secondary", action: closeModal },
      {
        label: "Сохранить",
        style: "primary",
        action: async () => {
          const name = $("#dlgRuleName").value.trim();
          const path = $("#dlgRulePath").value.trim();
          const safety = $("#dlgRuleSafety").value;
          const state = await settingsGuard(
            () => api().rule_save(editing ? rule.id : "", name, path, safety),
            "Правило не сохранено",
          );
          if (!state) return;
          closeModal();
          await applySettings(state, editing ? "Правило изменено" : "Правило добавлено");
        },
      },
    ],
  });
}

function confirmUninstall(id) {
  const app = programs && programs.apps.find((item) => item.id === id);
  if (!app) return;
  openModal({
    title: "Удалить программу?",
    body: `<div class="note"><b>${esc(app.name)}</b>${app.version ? ` ${esc(app.version)}` : ""}</div>
      <div class="note">Запустится штатный деинсталлятор Windows — возможно, с вопросом на экране.
      Остатки и папки настроек он не трогает.</div>`,
    buttons: [
      { label: "Отмена", style: "secondary", action: closeModal },
      {
        label: "Удалить",
        style: "primary",
        action: async () => {
          closeModal();
          status(`Удаление: ${app.name}…`, "busy");
          await api().programs_uninstall(id);
        },
      },
    ],
  });
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

/* ── страница «Очистка»: те же цели, но по уровню риска ── */

function cleanMatches(target) {
  if (state.mode === "easy" && !target.recommended) return false;
  if (!state.search) return true;
  const needle = state.search.toLowerCase();
  return (target.name + " " + target.description).toLowerCase().includes(needle);
}

function renderClean() {
  const groups = new Map();
  for (const target of state.targets) {
    if (!cleanMatches(target)) continue;
    if (!groups.has(target.safety)) groups.set(target.safety, []);
    groups.get(target.safety).push(target);
  }
  const order = SAFETY_GROUPS.map(([id]) => id);
  const entries = [...groups.entries()].sort(
    (a, b) => order.indexOf(a[0]) - order.indexOf(b[0]),
  );

  $("#cleanEmpty").hidden = entries.length > 0;
  $("#cleanGroups").innerHTML = entries.map(([safety, items]) => {
    const label = (SAFETY_GROUPS.find(([id]) => id === safety) || [safety, "Прочее"])[1];
    const selected = items.filter((t) => t.selected).length;
    const size = items.reduce((sum, t) => sum + (t.scanned ? t.size : 0), 0);
    const collapsed = state.collapsed.has(safety);
    return `
      <div class="group${collapsed ? " collapsed" : ""}" data-group="${safety}">
        <div class="group-head" data-toggle="${safety}">
          ${glyph("E70D", "chev")}
          <span class="g-title">${label}</span>
          <span class="g-meta">${selected ? `выбрано ${selected} · ` : ""}${items.length} цел.</span>
          <span class="g-size">${size ? bytes(size) : ""}</span>
        </div>
        <div class="group-body">${items.map(row).join("")}</div>
      </div>`;
  }).join("");
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
  const cleanChip = $("#cleanChip");
  cleanChip.textContent = chip.textContent;
  cleanChip.classList.toggle("muted-chip", !s.scanned);

  $("#pillAdmin").hidden = state.admin;
  $("#statusMeta").textContent = `${s.total} целей · ${s.scanned} проанализировано`
    + (s.errors ? ` · ошибок ${s.errors}` : "");
}

function render() {
  renderLayers();
  renderMix();
  renderTargets();
  renderClean();
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

async function showPreview() {
  const data = await api().preview();
  if (!data) {
    openModal({
      title: "Предпросмотр",
      body: `<div class="note">Отметьте цель с предпросмотром — покажем первые файлы внутри.</div>`,
      buttons: [{ label: "Закрыть", style: "secondary", action: closeModal }],
    });
    return;
  }
  const rows = data.files.length
    ? data.files.map((f) => `<li>${f.is_dir ? "📁" : "📄"} ${esc(f.name)}${
      f.size_text ? ` — ${f.size_text}` : ""}</li>`).join("")
    : "<li>Папка пуста или недоступна</li>";
  const foot = data.files.length
    ? `Показаны первые ${data.files.length} элементов — удаляется содержимое целиком.`
    : "";
  openModal({
    title: `Предпросмотр: ${esc(data.name)}`,
    wide: true,
    body: `<div class="note"><b>${esc(data.path)}</b><ul>${rows}</ul></div>${
      foot ? `<div class="note">${foot}</div>` : ""}`,
    buttons: [{ label: "Закрыть", style: "secondary", action: closeModal }],
  });
}

async function startScan() {
  if (state.busy) return;
  state.collapsed.clear();
  setProgress(null, "Анализ целей…");
  status("Анализ целей…", "busy");
  for (const btn of document.querySelectorAll(".js-scan")) btn.disabled = true;
  for (const btn of document.querySelectorAll(".js-stop")) btn.disabled = false;
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
    for (const btn of document.querySelectorAll(".js-scan")) btn.disabled = false;
    for (const btn of document.querySelectorAll(".js-stop")) btn.disabled = true;
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
  programsSizes(batch) {
    if (!programs) return;
    for (const item of batch) {
      const app = programs.apps.find((entry) => entry.id === item.id);
      if (app) app.size_text = item.size_text;
    }
    if (current === "programs") renderPrograms();
  },
  programsMeasured() {
    if (!programs) return;
    programs.measuring = false;
    if (current === "programs") renderPrograms();
    status("Размеры посчитаны", "");
  },
  dupProgress(scanned, text) {
    if (dup) dup.busy = true;
    $("#dupChip").textContent = `проверено ${scanned}`;
    status(text || "Ищем дубликаты…", "busy");
  },
  dupDone(state) {
    dup = state;
    dupChecked.clear();
    renderDup();
    status(
      state.count
        ? `Найдено групп: ${state.count} · зря занято ${state.wasted_text}`
        : "Дубликатов не найдено",
      "",
    );
  },
  disksSmart(payload) {
    if (!payload) return;
    disks = payload;
    if (current === "disks") {
      renderDisks();
      status(`SMART прочитан: дисков ${payload.disks.length}`, "");
    }
  },
  analyzerDone(payload) {
    if (!payload || current !== "analyzer") return;
    renderAnalyzerDone(payload);
    status(payload.cancelled ? "Анализ остановлен" : "Анализ завершён", "");
  },
  analyzerEmptied(payload) {
    if (!payload || current !== "analyzer") return;
    status(`Удалено пустых папок: ${payload.removed}`, "");
    const errors = (payload.errors || []).map((line) => `<li>${esc(line)}</li>`).join("");
    if (payload.report) renderAnalyzerDone({ ...payload.report, mode: "empty" });
    if (errors) {
      openModal({
        title: "Часть папок не удалена",
        body: `<div class="note"><ul>${errors}</ul></div>`,
        buttons: [{ label: "Понятно", style: "primary", action: closeModal }],
      });
    }
  },
  analyzerTreemap(payload) {
    if (!payload || current !== "analyzer") return;
    renderTreemap(payload);
    status(`Treemap: ${payload.nodes.length} элементов`, "");
  },
  elevateFailed(message) {
    status(message || "Не удалось получить права администратора", "err");
  },
  updateResult(payload) {
    if (!payload) return;
    const note = $("#setUpdateNote");
    if (!note) return;
    const message = payload.message
      + (payload.status === "available" && payload.url ? ` Страница: ${payload.url}` : "");
    note.textContent = message;
    status(message, payload.status === "error" ? "err" : "");
  },
  dupDeleted(result) {
    if (result.state) {
      dup = result.state;
      dupChecked.clear();
      renderDup();
    }
    status(`Удалено файлов: ${result.deleted} · освобождено ${result.freed_text}`, "");
    const errors = (result.errors || []).map((line) => `<li>${esc(line)}</li>`).join("");
    openModal({
      title: result.failed ? "Удалено с ошибками" : "Копии удалены",
      body: `<div class="note">Удалено: <b>${result.deleted}</b> · освобождено <b>${result.freed_text}</b>${
        result.failed ? ` · не удалось: <b>${result.failed}</b>` : ""
      }</div>${errors ? `<div class="note"><ul>${errors}</ul></div>` : ""}`,
      buttons: [{ label: "Готово", style: "primary", action: closeModal }],
    });
  },
  async programsUninstalled(payload) {
    const logs = (payload.logs || []).join("\n");
    if (payload.state) {
      programs = payload.state;
      renderPrograms();
    }
    status(payload.ok ? "Деинсталлятор запущен" : "Не удалось запустить удаление", "");
    openModal({
      title: payload.ok ? "Удаление запущено" : "Удаление невозможно",
      body: `<div class="note" style="white-space:pre-wrap">${esc(logs)}</div>`,
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

    const uninstall = event.target.closest("[data-uninstall]");
    if (uninstall) {
      confirmUninstall(uninstall.dataset.uninstall);
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

    // body тоже носит data-view (для CSS), поэтому исключаем его — иначе
    // эта ветка перехватывает ЛЮБОЙ клик и до кнопок шапки дело не доходит.
    const nav = event.target.closest("[data-view]:not(body)");
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

    if (event.target.classList.contains("scrim")) closeModal();
  });

  document.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    // Тащим окно за шапку: WM_NCLBUTTONDOWN работает только при зажатой
    // кнопке, поэтому перетаскивание — на mousedown, а не на click.
    if (event.target.closest("[data-drag]") || event.target.id === "titlebar") {
      event.preventDefault();
      api().win_drag();
      return;
    }
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
    if (current !== "deep" && current !== "clean") showView("deep");
    renderTargets();
    renderClean();
  });

  $("#homeDrive").addEventListener("change", (event) => pickDrive(event.target.value));
  $("#homeBannerBtn").addEventListener("click", () => showView("deep"));
  $("#histType").addEventListener("change", renderHistory);
  $("#progSearch").addEventListener("input", renderPrograms);
  $("#progDrive").addEventListener("change", renderPrograms);

  $("#startSearch").addEventListener("input", (event) => {
    startupSearch = event.target.value.trim();
    renderStartup();
  });
  $("#startList").addEventListener("change", (event) => {
    const box = event.target.closest("[data-start-toggle]");
    if (box) toggleStartup(box.dataset.startToggle, box.checked);
  });

  $("#dupPick").addEventListener("click", dupPick);
  $("#dupScan").addEventListener("click", dupScan);
  $("#dupStop").addEventListener("click", async () => {
    await api().dup_stop();
    status("Поиск остановлен", "");
  });
  $("#dupDelete").addEventListener("click", confirmDupDelete);
  $("#dupMode").addEventListener("click", (event) => {
    const item = event.target.closest("[data-mode]");
    if (!item) return;
    for (const other of document.querySelectorAll("#dupMode .seg-item")) {
      other.classList.toggle("on", other === item);
    }
  });
  $("#dupList").addEventListener("change", (event) => {
    const box = event.target.closest("[data-dup-file]");
    if (!box) return;
    const path = box.dataset.dupFile;
    if (box.checked) dupChecked.add(path);
    else dupChecked.delete(path);
    const top = $("#dupList").scrollTop;
    renderDup();
    $("#dupList").scrollTop = top;
  });
  $("#dupList").addEventListener("click", (event) => {
    const head = event.target.closest("[data-dup-group]");
    if (!head) return;
    const id = head.dataset.dupGroup;
    if (dupCollapsed.has(id)) dupCollapsed.delete(id);
    else dupCollapsed.add(id);
    const top = $("#dupList").scrollTop;
    renderDup();
    $("#dupList").scrollTop = top;
  });

  $("#btnScan").addEventListener("click", startScan);
  $("#diskRefresh").addEventListener("click", () => loadDisks(true));
  $("#pillAdmin").addEventListener("click", () => {
    openModal({
      title: "Права администратора",
      body: `<div class="note">Перезапустить приложение с правами администратора?
        Нужны они для системных целей глубокой очистки, SMART-атрибутов и VSS.
        Текущее окно закроется.</div>`,
      buttons: [
        { label: "Отмена", style: "secondary", action: closeModal },
        {
          label: "Перезапустить",
          style: "primary",
          action: async () => {
            closeModal();
            status("Запрашиваю UAC…", "busy");
            await api().elevate();
          },
        },
      ],
    });
  });

  // ── анализ ──
  $("#anaTop").addEventListener("click", () => anaRun("top", true));
  $("#anaFiles").addEventListener("click", () => anaRun("files", true));
  $("#anaEmpty").addEventListener("click", () => anaRun("empty", true));
  $("#anaTreemapBtn").addEventListener("click", anaShowTreemap);
  $("#anaRefresh").addEventListener("click", () => {
    if (anaTreemapOn) {
      anaChipText("treemap…");
      api().analyzer_treemap("", false);
    } else if (anaMode) anaRun(anaMode, true);
  });
  $("#anaStop").addEventListener("click", async () => {
    await api().analyzer_stop();
    anaChipText("останавливаем…");
  });
  $("#anaDrive").addEventListener("change", (e) => anaDriveChange(e.target.value));
  $("#anaExt").addEventListener("change", anaApplyFilters);
  $("#anaSize").addEventListener("change", anaApplyFilters);
  $("#anaAge").addEventListener("change", anaApplyFilters);
  $("#anaReset").addEventListener("click", () => {
    $("#anaExt").value = "";
    $("#anaSize").value = "10";
    $("#anaAge").value = "0";
    anaApplyFilters();
  });
  $("#anaBack").addEventListener("click", () => {
    anaChipText("treemap…");
    api().analyzer_treemap("", true);
  });
  $("#anaRemoveEmpty").addEventListener("click", () => {
    const chip = $("#anaChip").textContent || "";
    const count = Number((chip.match(/пустых папок: (\d+)/) || [])[1] || 0);
    openModal({
      title: "Пустые папки",
      body: `<div class="note">Удалить пустые папки?<br>
        Удаляются только папки без файлов и подпапок, корень сканирования защищён.</div>`,
      buttons: [
        { label: "Отмена", style: "secondary", action: closeModal },
        {
          label: "Удалить",
          style: "danger",
          action: async () => {
            closeModal();
            anaChipText("удаляем…");
            $("#anaRemoveEmpty").hidden = true;
            await api().analyzer_remove_empty();
          },
        },
      ],
    });
  });

  // ── настройки ──
  $("#setTheme").addEventListener("change", async (e) => {
    const state = await settingsGuard(() => api().settings_set("theme", e.target.value), "Тема не сохранена");
    if (state) await applySettings(state, "Тема применена");
  });
  for (const [id, key] of [
    ["setRecycle", "to_recycle"],
    ["setSafe", "safe_mode"],
    ["setRestore", "restore_point"],
  ]) {
    $(`#${id}`).addEventListener("change", async (e) => {
      const state = await settingsGuard(() => api().settings_set(key, e.target.checked), "Не сохранено");
      if (state) await applySettings(state, "Сохранено");
    });
  }
  $("#setThreshold").addEventListener("change", async (e) => {
    const state = await settingsGuard(
      () => api().settings_set("deep_threshold_gb", e.target.value), "Порог не сохранён",
    );
    if (state) await applySettings(state, "Порог сохранён");
  });
  $("#setAutostart").addEventListener("change", async (e) => {
    const state = await settingsGuard(() => api().autostart_set(e.target.checked), "Автозапуск не изменён");
    if (state) await applySettings(state, "Автозапуск обновлён");
    else e.target.checked = !e.target.checked;
  });
  $("#setDataDir").addEventListener("click", () => api().open_special("data"));
  $("#setLog").addEventListener("click", async () => {
    await settingsGuard(() => api().open_special("log"), "Не удалось открыть лог");
  });
  $("#setClearHistory").addEventListener("click", () => {
    openModal({
      title: "Очистка истории",
      body: '<div class="note">Удалить всю историю очисток? Это не удаляет файлы с диска.</div>',
      buttons: [
        { label: "Отмена", style: "secondary", action: closeModal },
        {
          label: "Удалить",
          style: "danger",
          action: async () => {
            closeModal();
            const state = await settingsGuard(() => api().history_clear(), "Не удалось очистить");
            if (state) await applySettings(state, "История очищена");
          },
        },
      ],
    });
  });
  $("#setExportJson").addEventListener("click", () => exportReport("json"));
  $("#setExportCsv").addEventListener("click", () => exportReport("csv"));
  $("#setRules").addEventListener("click", (e) => {
    const row = e.target.closest("[data-rule-id]");
    if (!row) return;
    setSelRule = row.dataset.ruleId;
    renderSettings();
  });
  $("#setRuleAdd").addEventListener("click", () => ruleDialog(null));
  $("#setRuleEdit").addEventListener("click", () => {
    const rule = (setst.rules || []).find((r) => r.id === setSelRule);
    if (!rule) {
      status("Выберите правило в списке", "err");
      return;
    }
    ruleDialog(rule);
  });
  $("#setRuleDelete").addEventListener("click", () => {
    const rule = (setst.rules || []).find((r) => r.id === setSelRule);
    if (!rule) {
      status("Выберите правило в списке", "err");
      return;
    }
    openModal({
      title: "Удаление правила",
      body: `<div class="note">Удалить правило «${esc(rule.name)}»?<br>
        Файлы на диске не удаляются — правило исчезнет из списка целей.</div>`,
      buttons: [
        { label: "Отмена", style: "secondary", action: closeModal },
        {
          label: "Удалить",
          style: "danger",
          action: async () => {
            closeModal();
            const state = await settingsGuard(() => api().rule_delete(rule.id), "Не удалось удалить");
            if (state) {
              setSelRule = "";
              await applySettings(state, "Правило удалено");
            }
          },
        },
      ],
    });
  });
  $("#setWlAdd").addEventListener("click", async () => {
    const path = $("#setWlInput").value.trim();
    if (!path) return;
    const state = await settingsGuard(() => api().whitelist_add(path), "Путь не добавлен");
    if (state) {
      $("#setWlInput").value = "";
      await applySettings(state, "Путь добавлен в белый список");
    }
  });
  $("#setWhitelist").addEventListener("click", (e) => {
    const row = e.target.closest("[data-wl-path]");
    if (!row) return;
    setSelWl = row.dataset.wlPath;
    renderSettings();
  });
  $("#setWlRemove").addEventListener("click", async () => {
    if (!setSelWl) {
      status("Выберите путь в списке", "err");
      return;
    }
    const state = await settingsGuard(() => api().whitelist_remove(setSelWl), "Не удалось удалить");
    if (state) {
      setSelWl = "";
      await applySettings(state, "Путь убран из белого списка");
    }
  });
  $("#setSchedInstall").addEventListener("click", async () => {
    const state = await settingsGuard(
      () => api().schedule_install($("#setDay").value, $("#setTime").value.trim(), $("#setMode").value),
      "Не удалось создать задание",
    );
    if (state) await applySettings(state, "Задание создано");
  });
  $("#setSchedRemove").addEventListener("click", async () => {
    const state = await settingsGuard(() => api().schedule_remove(), "Не удалось удалить задание");
    if (state) await applySettings(state, "Задание удалено");
  });
  $("#setCfgExport").addEventListener("click", async () => {
    const result = await settingsGuard(() => api().config_export(), "Экспорт не удался");
    if (result && result.ok) status(`Настройки экспортированы: ${result.path}`);
  });
  $("#setCfgImport").addEventListener("click", async () => {
    const result = await settingsGuard(() => api().config_import(), "Импорт не удался");
    if (result && result.ok) {
      const stats = result.stats;
      await loadSettings();
      openModal({
        title: "Импорт настроек",
        body: `<div class="note">Настроек применено: <b>${stats.config}</b> ·
          правил добавлено: <b>${stats.rules}</b>${
          (stats.skipped || []).length
            ? `<br><br>Пропущено:<ul>${stats.skipped.slice(0, 8).map((s) => `<li>${esc(s)}</li>`).join("")}</ul>`
            : ""
        }</div>`,
        buttons: [{ label: "Готово", style: "primary", action: closeModal }],
      });
    }
  });
  $("#setUpdateSource").addEventListener("change", async (e) => {
    const state = await settingsGuard(
      () => api().settings_set("update_source", e.target.value.trim()), "Источник не сохранён",
    );
    if (state) await applySettings(state, "Источник обновлений сохранён");
  });
  $("#setCheckUpdates").addEventListener("click", async () => {
    $("#setUpdateNote").textContent = "Проверяю обновления…";
    await api().check_updates();
  });
  $("#btnStop").addEventListener("click", stopScan);
  $("#btnSafe").addEventListener("click", async () => applyPayload(await api().safe_set()));
  $("#btnNone").addEventListener("click", async () => applyPayload(await api().deselect_all()));
  $("#btnPlan").addEventListener("click", showPlan);
  $("#btnClean").addEventListener("click", showPlan);

  for (const btn of document.querySelectorAll(".js-scan")) {
    btn.addEventListener("click", startScan);
  }
  for (const btn of document.querySelectorAll(".js-stop")) {
    btn.addEventListener("click", stopScan);
  }

  $("#cleanMode").addEventListener("click", (event) => {
    const item = event.target.closest("[data-mode]");
    if (!item) return;
    state.mode = item.dataset.mode;
    for (const other of document.querySelectorAll("#cleanMode .seg-item")) {
      other.classList.toggle("on", other === item);
    }
    renderClean();
  });

  $("#btnPreview").addEventListener("click", showPreview);

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
