#!/usr/bin/env python3
"""Build a self-contained HTML page from the strings CSV."""
from pathlib import Path
import json
import csv
import re

ROOT = Path(__file__).parent
CSV_PATH = ROOT / "string_performance_database.csv"
OUT_PATH = ROOT / "strings.html"

# Load CSV
with CSV_PATH.open(newline="") as f:
    reader = csv.reader(f)
    rows = list(reader)

headers = rows[0]
data = rows[1:]

# Determine column types by sampling values (skip empty / NA).
# Some columns (e.g. "Gauge Acutal (mm)") mix entries like "1.2 x" with regular
# numbers; treat those as numeric and parse out the leading float.
NUM_RE = re.compile(r"^\s*-?\d+(?:\.\d+)?")

def parse_num(v: str):
    if v is None: return None
    s = v.strip()
    if s == "" or s.upper() == "NA": return None
    try:
        return float(s)
    except ValueError:
        m = NUM_RE.match(s)
        return float(m.group(0)) if m else None

col_types = []  # "number" | "string"
unique_counts = []
for ci, h in enumerate(headers):
    vals = [r[ci] for r in data if ci < len(r)]
    non_empty = [v for v in vals if v != "" and v.strip().upper() != "NA"]
    # Numeric if at least 80% of non-empty values can be parsed as numbers.
    if non_empty:
        parsed_ok = sum(1 for v in non_empty if parse_num(v) is not None)
        is_num = parsed_ok / len(non_empty) >= 0.8
    else:
        is_num = False
    col_types.append("number" if is_num else "string")
    unique_counts.append(len(set(non_empty)))

# Decide categorical: string column OR very low cardinality (<= 8) numeric/string
categorical = []
for ci, h in enumerate(headers):
    uc = unique_counts[ci]
    if ci == 0:
        categorical.append(False)  # name column = freetext search
        continue
    if uc <= 8:
        categorical.append(True)
    else:
        categorical.append(False)

# Convert numeric values to floats (or None) for JS use
js_rows = []
for r in data:
    obj = []
    for ci in range(len(headers)):
        v = r[ci] if ci < len(r) else ""
        if col_types[ci] == "number":
            obj.append(parse_num(v))
        else:
            obj.append(v)
    js_rows.append(obj)

# Collect unique values for categorical columns
uniques = {}
for ci, is_cat in enumerate(categorical):
    if is_cat:
        seen = []
        seen_set = set()
        for r in js_rows:
            v = r[ci]
            key = "" if v is None else v
            if key not in seen_set:
                seen_set.add(key)
                seen.append(v)
        # Sort: numbers ascending, strings alpha
        if col_types[ci] == "number":
            seen.sort(key=lambda x: (x is None, x if x is not None else 0))
        else:
            seen.sort(key=lambda x: (x is None or x == "", str(x).lower()))
        uniques[ci] = seen

meta = {
    "headers": headers,
    "types": col_types,
    "categorical": categorical,
    "uniques": uniques,
}

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Tennis String Performance Database</title>
<style>
  :root {
    --bg: #0e1116;
    --panel: #161b22;
    --panel-2: #1c2230;
    --border: #2a3140;
    --text: #e6edf3;
    --muted: #8b949e;
    --accent: #4dabf7;
    --accent-2: #ffd43b;
    --good: #51cf66;
    --bad: #ff6b6b;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text); font: 13px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  header { padding: 18px 22px; border-bottom: 1px solid var(--border); display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; background: var(--panel); }
  header h1 { margin: 0; font-size: 18px; letter-spacing: 0.2px; }
  header .sub { color: var(--muted); font-size: 12px; }
  header .stats { margin-left: auto; color: var(--muted); font-size: 12px; }
  header .stats strong { color: var(--text); }

  .toolbar { padding: 10px 22px; display: flex; gap: 10px; align-items: center; border-bottom: 1px solid var(--border); background: var(--panel); flex-wrap: wrap; }
  .toolbar input[type="search"] { flex: 1; min-width: 220px; background: var(--panel-2); border: 1px solid var(--border); color: var(--text); padding: 8px 12px; border-radius: 6px; font: inherit; }
  .toolbar button { background: var(--panel-2); border: 1px solid var(--border); color: var(--text); padding: 7px 12px; border-radius: 6px; font: inherit; cursor: pointer; }
  .toolbar button:hover { border-color: var(--accent); color: var(--accent); }
  .toolbar .toggle { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); cursor: pointer; user-select: none; }
  .toolbar .hint { color: var(--muted); font-size: 11px; margin-left: 4px; }

  .wrap { overflow: auto; max-height: calc(100vh - 130px); position: relative; }
  table { border-collapse: separate; border-spacing: 0; width: max-content; min-width: 100%; }
  th, td { padding: 6px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; font-variant-numeric: tabular-nums; }
  thead tr:first-child th { position: sticky; top: 0; z-index: 3; background: var(--panel); border-bottom: 1px solid var(--border); }
  thead .filter-row th { position: sticky; background: var(--panel-2); padding: 4px 6px; z-index: 3; border-bottom: 1px solid var(--border); }
  /* `top` for filter-row cells is set dynamically in JS to match header height. */
  th.col-name, td.col-name { position: sticky; left: 0; background: var(--panel); z-index: 2; }
  tbody td.col-name { background: var(--bg); border-right: 1px solid var(--border); font-weight: 500; }
  thead tr:first-child th.col-name { z-index: 5; }
  thead .filter-row th.col-name { z-index: 4; background: var(--panel-2); }

  th.sortable { cursor: pointer; user-select: none; }
  th.sortable:hover { color: var(--accent); }
  th .sort-indicator { display: inline-flex; align-items: baseline; gap: 2px; color: var(--accent-2); margin-left: 4px; font-size: 11px; }
  th .sort-indicator .sort-pri { font-size: 9px; opacity: 0.75; }

  /* Selection column */
  th.col-sel, td.col-sel { position: sticky; left: 0; width: 32px; min-width: 32px; padding: 4px 6px; text-align: center; background: var(--panel); z-index: 2; }
  tbody td.col-sel { background: var(--bg); border-right: 1px solid var(--border); }
  thead tr:first-child th.col-sel { z-index: 5; }
  thead .filter-row th.col-sel { z-index: 4; background: var(--panel-2); }
  /* When col-sel exists, col-name's sticky left becomes the width of col-sel */
  th.col-name, td.col-name { left: 32px; }
  td.col-sel input[type="checkbox"], th.col-sel input[type="checkbox"] { cursor: pointer; margin: 0; vertical-align: middle; }
  tbody tr.selected td { background: rgba(255, 212, 59, 0.10); }
  tbody tr.selected td.col-name { background: #2a2616; }
  tbody tr.selected td.col-sel { background: #2a2616; }

  tbody tr:hover td { background: rgba(77, 171, 247, 0.08); }
  tbody tr:hover td.col-name { background: #1d2330; }

  /* Column-picker dropdown */
  .col-picker-wrap { position: relative; display: inline-block; }
  .col-picker-panel { position: absolute; top: calc(100% + 4px); right: 0; background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px; padding: 8px; min-width: 240px; max-height: 60vh; overflow: auto; z-index: 10; box-shadow: 0 8px 24px rgba(0,0,0,0.4); display: none; }
  .col-picker-panel.open { display: block; }
  .col-picker-panel .cp-row { display: flex; align-items: center; gap: 6px; padding: 3px 4px; border-radius: 4px; cursor: pointer; }
  .col-picker-panel .cp-row:hover { background: rgba(77,171,247,0.10); }
  .col-picker-panel .cp-row input { margin: 0; cursor: pointer; }
  .col-picker-panel .cp-row label { flex: 1; cursor: pointer; user-select: none; }
  .col-picker-panel .cp-actions { display: flex; gap: 6px; padding: 4px 0 8px; border-bottom: 1px solid var(--border); margin-bottom: 6px; }
  .col-picker-panel .cp-actions button { flex: 1; background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 4px 6px; border-radius: 4px; font: 11px inherit; cursor: pointer; }
  .col-picker-panel .cp-actions button:hover { border-color: var(--accent); color: var(--accent); }

  .filter-input, .filter-select { width: 100%; min-width: 90px; background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 3px 5px; border-radius: 4px; font: 11px/1.3 inherit; }
  .filter-input:focus, .filter-select:focus { outline: none; border-color: var(--accent); }
  .num-range { display: flex; gap: 3px; }
  .num-range input { width: 50%; min-width: 0; }
  .clear-x { float: right; background: transparent; border: 0; color: var(--muted); cursor: pointer; padding: 0 2px; font-size: 10px; }
  .clear-x:hover { color: var(--bad); }

  .right { text-align: right; }
  td.num { text-align: right; }

  td.empty { color: var(--muted); font-style: italic; }

  /* tiny color heat for some interesting cols */
  .heat-good { color: var(--good); }
  .heat-bad { color: var(--bad); }
</style>
</head>
<body>
<header>
  <h1>Tennis String Performance Database</h1>
  <span class="sub">All polyester, 51 lb ref. tension, fast swing speed</span>
  <span class="stats"><strong id="count">0</strong> of <strong id="total">0</strong> strings · <strong id="selCount">0</strong> selected</span>
</header>
<div class="toolbar">
  <input id="globalSearch" type="search" placeholder="Search any column…" autocomplete="off">
  <label class="toggle"><input type="checkbox" id="selectedOnly"> show selected only</label>
  <button id="clearSelBtn">Clear selection</button>
  <button id="resetBtn">Reset filters &amp; sort</button>
  <button id="copyVisible">Copy visible (TSV)</button>
  <span class="col-picker-wrap">
    <button id="colPickerBtn" aria-haspopup="true" aria-expanded="false">Columns <span id="colPickerCount" style="color: var(--muted); font-weight: normal;"></span> ▾</button>
    <div class="col-picker-panel" id="colPickerPanel" role="menu"></div>
  </span>
  <span class="hint">click header to sort · shift-click to add to multi-sort · click again to flip · third click removes</span>
</div>
<div class="wrap">
  <table id="tbl">
    <thead>
      <tr id="headerRow"></tr>
      <tr class="filter-row" id="filterRow"></tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
</div>

<script>
const META = __META__;
const ROWS = __ROWS__;

const headers = META.headers;
const types = META.types;
const categorical = META.categorical;
const uniques = META.uniques;

const headerRow = document.getElementById("headerRow");
const filterRow = document.getElementById("filterRow");
const tbody = document.getElementById("tbody");
const countEl = document.getElementById("count");
const totalEl = document.getElementById("total");
const selCountEl = document.getElementById("selCount");
const globalSearch = document.getElementById("globalSearch");
const selectedOnlyToggle = document.getElementById("selectedOnly");
totalEl.textContent = ROWS.length;

// Sort state: ordered list of { col, dir }. First entry has highest priority.
// dir: 1 asc, -1 desc.
let sortState = [];
const filters = {}; // col index -> filter state
const selected = new Set(); // row index into ROWS
const hiddenCols = new Set(); // col indices that are currently hidden

// ----- Hidden-column persistence -----
const HIDDEN_STORAGE_KEY = "tennisStrings:hiddenCols:v1";
try {
  const saved = JSON.parse(localStorage.getItem(HIDDEN_STORAGE_KEY) || "[]");
  if (Array.isArray(saved)) saved.forEach(i => {
    if (Number.isInteger(i) && i >= 0 && i < headers.length) hiddenCols.add(i);
  });
} catch (e) { /* ignore */ }
function saveHiddenCols() {
  try { localStorage.setItem(HIDDEN_STORAGE_KEY, JSON.stringify([...hiddenCols])); } catch (e) {}
}

// ----- Selection column (leftmost) -----
const selTh = document.createElement("th");
selTh.className = "col-sel";
const selectAllBox = document.createElement("input");
selectAllBox.type = "checkbox";
selectAllBox.title = "Select/deselect all visible";
selTh.appendChild(selectAllBox);
headerRow.appendChild(selTh);

const selFilterTh = document.createElement("th");
selFilterTh.className = "col-sel";
filterRow.appendChild(selFilterTh);

selectAllBox.addEventListener("click", (e) => {
  // Toggle: if any currently-visible row is unselected, select all visible; otherwise clear visible.
  const visibleIdx = lastFilteredIdx;
  const anyUnselected = visibleIdx.some(i => !selected.has(i));
  if (anyUnselected) visibleIdx.forEach(i => selected.add(i));
  else visibleIdx.forEach(i => selected.delete(i));
  render();
});

// Build header + filter row
headers.forEach((h, ci) => {
  const th = document.createElement("th");
  th.textContent = h;
  th.className = "sortable" + (ci === 0 ? " col-name" : (types[ci] === "number" ? " right" : ""));
  const indicator = document.createElement("span");
  indicator.className = "sort-indicator";
  indicator.dataset.col = ci;
  th.appendChild(indicator);
  th.addEventListener("click", (e) => {
    const existingIdx = sortState.findIndex(s => s.col === ci);
    if (e.shiftKey) {
      // Multi-sort: cycle this column's state without disturbing others.
      if (existingIdx === -1) sortState.push({ col: ci, dir: 1 });
      else if (sortState[existingIdx].dir === 1) sortState[existingIdx].dir = -1;
      else sortState.splice(existingIdx, 1);
    } else {
      // Plain click: cycle THIS column, replace chain entirely.
      if (existingIdx === -1) sortState = [{ col: ci, dir: 1 }];
      else if (sortState.length === 1 && sortState[0].dir === 1) sortState = [{ col: ci, dir: -1 }];
      else if (sortState.length === 1 && sortState[0].dir === -1) sortState = [];
      else sortState = [{ col: ci, dir: 1 }];
    }
    render();
  });
  headerRow.appendChild(th);

  const fth = document.createElement("th");
  if (ci === 0) fth.className = "col-name";
  if (categorical[ci]) {
    const sel = document.createElement("select");
    sel.className = "filter-select";
    const allOpt = document.createElement("option");
    allOpt.value = "__all__"; allOpt.textContent = "All";
    sel.appendChild(allOpt);
    uniques[ci].forEach(v => {
      const opt = document.createElement("option");
      const display = v === null || v === "" ? "(empty)" : String(v);
      opt.value = display === "(empty)" ? "__empty__" : display;
      opt.textContent = display;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", () => {
      filters[ci] = sel.value === "__all__" ? null : { kind: "cat", value: sel.value };
      render();
    });
    fth.appendChild(sel);
  } else if (types[ci] === "number") {
    const wrap = document.createElement("div");
    wrap.className = "num-range";
    const min = document.createElement("input");
    min.className = "filter-input"; min.type = "number"; min.placeholder = "min"; min.step = "any";
    const max = document.createElement("input");
    max.className = "filter-input"; max.type = "number"; max.placeholder = "max"; max.step = "any";
    const update = () => {
      const lo = min.value === "" ? null : parseFloat(min.value);
      const hi = max.value === "" ? null : parseFloat(max.value);
      filters[ci] = (lo === null && hi === null) ? null : { kind: "range", lo, hi };
      render();
    };
    min.addEventListener("input", update);
    max.addEventListener("input", update);
    wrap.appendChild(min); wrap.appendChild(max);
    fth.appendChild(wrap);
  } else {
    const inp = document.createElement("input");
    inp.className = "filter-input";
    inp.type = "search";
    inp.placeholder = "contains…";
    inp.addEventListener("input", () => {
      filters[ci] = inp.value.trim() === "" ? null : { kind: "text", value: inp.value.toLowerCase() };
      render();
    });
    fth.appendChild(inp);
  }
  filterRow.appendChild(fth);
});

// ----- Column picker -----
const colPickerBtn = document.getElementById("colPickerBtn");
const colPickerPanel = document.getElementById("colPickerPanel");
const colPickerCount = document.getElementById("colPickerCount");

// Actions row
const cpActions = document.createElement("div");
cpActions.className = "cp-actions";
const cpShowAll = document.createElement("button");
cpShowAll.type = "button";
cpShowAll.textContent = "Show all";
const cpHideAll = document.createElement("button");
cpHideAll.type = "button";
cpHideAll.textContent = "Hide all";
cpActions.appendChild(cpShowAll);
cpActions.appendChild(cpHideAll);
colPickerPanel.appendChild(cpActions);

const cpCheckboxes = [];
headers.forEach((h, ci) => {
  const row = document.createElement("div");
  row.className = "cp-row";
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.id = "cp-cb-" + ci;
  cb.checked = !hiddenCols.has(ci);
  const lab = document.createElement("label");
  lab.htmlFor = cb.id;
  lab.textContent = h || "(col " + ci + ")";
  cb.addEventListener("change", () => {
    if (cb.checked) hiddenCols.delete(ci); else hiddenCols.add(ci);
    saveHiddenCols();
    applyColumnVisibility();
    updateColPickerCount();
  });
  row.appendChild(cb);
  row.appendChild(lab);
  colPickerPanel.appendChild(row);
  cpCheckboxes.push(cb);
});

function updateColPickerCount() {
  const hidden = hiddenCols.size;
  colPickerCount.textContent = hidden > 0 ? "(" + (headers.length - hidden) + "/" + headers.length + ")" : "";
}
updateColPickerCount();

cpShowAll.addEventListener("click", () => {
  hiddenCols.clear();
  cpCheckboxes.forEach(cb => cb.checked = true);
  saveHiddenCols();
  applyColumnVisibility();
  updateColPickerCount();
});
cpHideAll.addEventListener("click", () => {
  hiddenCols.clear();
  headers.forEach((_, ci) => hiddenCols.add(ci));
  cpCheckboxes.forEach(cb => cb.checked = false);
  saveHiddenCols();
  applyColumnVisibility();
  updateColPickerCount();
});

colPickerBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const isOpen = colPickerPanel.classList.toggle("open");
  colPickerBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
});
document.addEventListener("click", (e) => {
  if (!colPickerPanel.contains(e.target) && e.target !== colPickerBtn) {
    colPickerPanel.classList.remove("open");
    colPickerBtn.setAttribute("aria-expanded", "false");
  }
});

function applyColumnVisibility() {
  // Header cells: index 0 is the selection col, then headers[] map to indices 1..N.
  const headerCells = headerRow.children;
  const filterCells = filterRow.children;
  for (let ci = 0; ci < headers.length; ci++) {
    const disp = hiddenCols.has(ci) ? "none" : "";
    if (headerCells[ci + 1]) headerCells[ci + 1].style.display = disp;
    if (filterCells[ci + 1]) filterCells[ci + 1].style.display = disp;
  }
  // Body rows
  for (const tr of tbody.children) {
    const cells = tr.children; // [0] = selection cell
    for (let ci = 0; ci < headers.length; ci++) {
      if (cells[ci + 1]) cells[ci + 1].style.display = hiddenCols.has(ci) ? "none" : "";
    }
  }
  syncStickyOffsets();
}

document.getElementById("resetBtn").addEventListener("click", () => {
  filterRow.querySelectorAll("input").forEach(i => { if (i.type !== "checkbox") i.value = ""; });
  filterRow.querySelectorAll("select").forEach(s => s.selectedIndex = 0);
  for (const k in filters) delete filters[k];
  globalSearch.value = "";
  sortState = [];
  selectedOnlyToggle.checked = false;
  render();
});

document.getElementById("clearSelBtn").addEventListener("click", () => {
  selected.clear();
  selectedOnlyToggle.checked = false;
  render();
});

selectedOnlyToggle.addEventListener("change", render);
globalSearch.addEventListener("input", render);

let lastFilteredIdx = []; // indices of currently rendered rows (in ROWS)

function passes(row, rowIdx) {
  if (selectedOnlyToggle.checked && !selected.has(rowIdx)) return false;
  const gs = globalSearch.value.trim().toLowerCase();
  if (gs) {
    let hit = false;
    for (let i = 0; i < row.length; i++) {
      const v = row[i];
      if (v !== null && v !== undefined && String(v).toLowerCase().includes(gs)) { hit = true; break; }
    }
    if (!hit) return false;
  }
  for (const k in filters) {
    const f = filters[k]; if (!f) continue;
    const ci = +k;
    const v = row[ci];
    if (f.kind === "cat") {
      if (f.value === "__empty__") {
        if (!(v === null || v === "")) return false;
      } else {
        if (String(v) !== f.value) return false;
      }
    } else if (f.kind === "range") {
      if (v === null || v === undefined) return false;
      if (f.lo !== null && v < f.lo) return false;
      if (f.hi !== null && v > f.hi) return false;
    } else if (f.kind === "text") {
      if (v === null || v === undefined) return false;
      if (!String(v).toLowerCase().includes(f.value)) return false;
    }
  }
  return true;
}

function syncStickyOffsets() {
  // Align the filter-row's sticky top to the actual height of the header row,
  // so there's never a gap or overlap when the table scrolls.
  const h = headerRow.getBoundingClientRect().height;
  filterRow.querySelectorAll("th").forEach(th => { th.style.top = h + "px"; });
}
window.addEventListener("resize", syncStickyOffsets);

function cmp(a, b, ci, dir) {
  const av = a[ci], bv = b[ci];
  const aNull = av === null || av === undefined || av === "";
  const bNull = bv === null || bv === undefined || bv === "";
  if (aNull && bNull) return 0;
  if (aNull) return 1;
  if (bNull) return -1;
  if (types[ci] === "number") return (av - bv) * dir;
  return String(av).localeCompare(String(bv)) * dir;
}

function render() {
  // Sort indicators: clear, then mark each column in the sort chain with arrow + priority.
  const indicators = filterRow.parentElement.querySelectorAll(".sort-indicator");
  indicators.forEach(s => { s.textContent = ""; });
  sortState.forEach((s, i) => {
    const ind = indicators[s.col];
    if (!ind) return;
    const arrow = s.dir === 1 ? "▲" : "▼";
    if (sortState.length > 1) {
      ind.innerHTML = arrow + '<span class="sort-pri">' + (i + 1) + '</span>';
    } else {
      ind.textContent = arrow;
    }
  });

  // Filter: keep stable indices into ROWS so selection persists across sort/filter.
  const filteredIdx = [];
  for (let i = 0; i < ROWS.length; i++) {
    if (passes(ROWS[i], i)) filteredIdx.push(i);
  }

  if (sortState.length > 0) {
    filteredIdx.sort((ia, ib) => {
      const a = ROWS[ia], b = ROWS[ib];
      for (const s of sortState) {
        const c = cmp(a, b, s.col, s.dir);
        if (c !== 0) return c;
      }
      return ia - ib; // stable tie-break by original order
    });
  }

  lastFilteredIdx = filteredIdx;
  countEl.textContent = filteredIdx.length;
  selCountEl.textContent = selected.size;

  // Update select-all checkbox state based on currently visible rows
  if (filteredIdx.length === 0) {
    selectAllBox.checked = false;
    selectAllBox.indeterminate = false;
  } else {
    const allSel = filteredIdx.every(i => selected.has(i));
    const someSel = filteredIdx.some(i => selected.has(i));
    selectAllBox.checked = allSel;
    selectAllBox.indeterminate = !allSel && someSel;
  }

  // Render via documentFragment for speed
  const frag = document.createDocumentFragment();
  for (const ri of filteredIdx) {
    const row = ROWS[ri];
    const tr = document.createElement("tr");
    tr.dataset.idx = ri;
    if (selected.has(ri)) tr.className = "selected";

    // selection cell
    const selTd = document.createElement("td");
    selTd.className = "col-sel";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = selected.has(ri);
    cb.addEventListener("click", (e) => {
      e.stopPropagation();
      if (cb.checked) selected.add(ri); else selected.delete(ri);
      tr.classList.toggle("selected", cb.checked);
      selCountEl.textContent = selected.size;
      // Update select-all indicator
      const allSel = lastFilteredIdx.every(i => selected.has(i));
      const someSel = lastFilteredIdx.some(i => selected.has(i));
      selectAllBox.checked = allSel;
      selectAllBox.indeterminate = !allSel && someSel;
    });
    selTd.appendChild(cb);
    tr.appendChild(selTd);

    for (let ci = 0; ci < headers.length; ci++) {
      const td = document.createElement("td");
      const v = row[ci];
      if (ci === 0) td.className = "col-name";
      else if (types[ci] === "number") td.className = "num";
      if (v === null || v === undefined || v === "") {
        td.classList.add("empty");
        td.textContent = "—";
      } else {
        if (types[ci] === "number") {
          const n = v;
          td.textContent = Number.isInteger(n) ? String(n) : (Math.abs(n) >= 100 ? n.toFixed(1) : n.toFixed(2));
        } else {
          td.textContent = String(v);
        }
      }
      tr.appendChild(td);
    }
    frag.appendChild(tr);
  }
  tbody.replaceChildren(frag);
  applyColumnVisibility();
}

document.getElementById("copyVisible").addEventListener("click", async () => {
  const visibleHeaders = headers.filter((_, ci) => !hiddenCols.has(ci));
  const lines = [visibleHeaders.join("\\t")];
  const rows = tbody.querySelectorAll("tr");
  rows.forEach(tr => {
    // Skip the first cell (selection checkbox column); skip hidden columns.
    const dataCells = [...tr.children].slice(1);
    const cells = dataCells
      .filter((_, ci) => !hiddenCols.has(ci))
      .map(td => td.textContent === "—" ? "" : td.textContent);
    lines.push(cells.join("\\t"));
  });
  try {
    await navigator.clipboard.writeText(lines.join("\\n"));
    const btn = document.getElementById("copyVisible");
    const orig = btn.textContent;
    btn.textContent = "Copied " + (rows.length) + " rows";
    setTimeout(() => btn.textContent = orig, 1500);
  } catch (e) {
    alert("Copy failed: " + e.message);
  }
});

render();
syncStickyOffsets();
</script>
</body>
</html>
"""

html = HTML.replace("__META__", json.dumps(meta)).replace("__ROWS__", json.dumps(js_rows))
OUT_PATH.write_text(html)
print(f"Wrote {OUT_PATH} ({len(html):,} bytes, {len(js_rows)} rows, {len(headers)} cols)")
