const state = {
  allItems: [],
  market: "all",
  keyword: "",
};

const marketLabels = {
  all: "全部",
  cn: "A股",
  hk: "港股",
};

function formatTime(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", { hour12: false });
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
}

function makeStatusLabel(code) {
  if (code === "fresh") return "最新";
  if (code === "stale") return "延迟";
  if (code === "old") return "过旧";
  return "未知";
}

function renderMetrics(generatedAt, items) {
  const metrics = document.getElementById("metrics");
  const totalRecords = items.reduce((acc, item) => acc + Number(item.total_records || 0), 0);
  const periodCount = items.reduce((acc, item) => acc + Number(item.period_count || 0), 0);

  const cards = [
    { label: "标的数量", value: formatNumber(items.length) },
    { label: "周期桶总数", value: formatNumber(periodCount) },
    { label: "累计记录", value: formatNumber(totalRecords) },
    { label: "页面数据更新时间", value: formatTime(generatedAt) },
  ];

  metrics.innerHTML = cards
    .map(
      (card) => `<article class="metric-card"><div class="label">${card.label}</div><div class="value">${card.value}</div></article>`,
    )
    .join("");
}

function renderFilters(items) {
  const marketSet = new Set(items.map((item) => item.market));
  const chips = ["all", ...Array.from(marketSet).sort()]
    .map((market) => {
      const isActive = market === state.market ? "active" : "";
      const label = marketLabels[market] || market.toUpperCase();
      return `<button class="chip ${isActive}" data-market="${market}">${label}</button>`;
    })
    .join("");

  const filters = document.getElementById("marketFilters");
  filters.innerHTML = chips;
  filters.querySelectorAll(".chip").forEach((node) => {
    node.addEventListener("click", () => {
      state.market = node.dataset.market;
      renderFilters(state.allItems);
      renderTable();
    });
  });
}

function filteredItems() {
  const keyword = state.keyword.trim().toLowerCase();
  return state.allItems.filter((item) => {
    if (state.market !== "all" && item.market !== state.market) return false;
    if (!keyword) return true;
    const code = String(item.code || "").toLowerCase();
    const name = String(item.name || "").toLowerCase();
    return code.includes(keyword) || name.includes(keyword);
  });
}

function renderTable() {
  const rows = filteredItems();
  const body = document.getElementById("tableBody");
  const empty = document.getElementById("emptyState");

  if (!rows.length) {
    body.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  const sorted = [...rows].sort((a, b) => {
    const aFetch = new Date(a.latest_fetch_time || 0).getTime();
    const bFetch = new Date(b.latest_fetch_time || 0).getTime();
    return bFetch - aFetch;
  });

  body.innerHTML = sorted
    .map((item) => {
      const periods = Object.keys(item.periods || {}).sort();
      const badges = periods.map((p) => `<span class="badge">${p}</span>`).join("");
      const statusText = makeStatusLabel(item.status);
      const market = marketLabels[item.market] || item.market;
      return `
      <tr>
        <td>${market}</td>
        <td>
          <div class="code">${item.code}</div>
          <div class="name">${item.name || "-"}</div>
        </td>
        <td><span class="status-pill status-${item.status}">${statusText}</span></td>
        <td><div class="badges">${badges || '<span class="badge">-</span>'}</div></td>
        <td>${formatNumber(item.total_records)}</td>
        <td>${formatTime(item.latest_fetch_time)}</td>
        <td>${formatTime(item.latest_data_time)}</td>
      </tr>`;
    })
    .join("");
}

async function init() {
  const resp = await fetch("./status-data.json", { cache: "no-store" });
  if (!resp.ok) {
    throw new Error(`status-data.json load failed: ${resp.status}`);
  }
  const payload = await resp.json();
  const items = Array.isArray(payload.items) ? payload.items : [];
  state.allItems = items;

  renderMetrics(payload.generated_at, items);
  renderFilters(items);
  renderTable();

  document.getElementById("searchInput").addEventListener("input", (event) => {
    state.keyword = event.target.value;
    renderTable();
  });
}

init().catch((err) => {
  document.getElementById("tableBody").innerHTML = `
    <tr>
      <td colspan="7">加载失败：${err.message}</td>
    </tr>
  `;
});
