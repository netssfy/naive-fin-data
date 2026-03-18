const state = {
  allItems: [],
  market: "all",
  keyword: "",
};

const marketLabels = {
  all: "All",
  cn: "CN",
  hk: "HK",
};

function formatTime(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", {
    hour12: false,
    timeZone: "Asia/Shanghai",
  });
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
}

function makeStatusLabel(code) {
  if (code === "fresh") return "latest";
  if (code === "stale") return "stale";
  if (code === "old") return "old";
  return "unknown";
}

function periodOrder(period) {
  const order = ["1m", "5m", "15m", "30m", "60m", "1d", "daily", "1w", "weekly", "1mo", "monthly"];
  const idx = order.indexOf(period);
  return idx >= 0 ? idx : 999;
}

function renderMetrics(generatedAt, items) {
  const metrics = document.getElementById("metrics");
  const totalRecords = items.reduce((acc, item) => acc + Number(item.total_records || 0), 0);
  const periodCount = items.reduce((acc, item) => acc + Number(item.period_count || 0), 0);
  const freshCount = items.filter((x) => x.status === "fresh").length;

  const cards = [
    { label: "Symbols", value: formatNumber(items.length) },
    { label: "Period Buckets", value: formatNumber(periodCount) },
    { label: "Total Records", value: formatNumber(totalRecords) },
    { label: "Fresh Symbols", value: formatNumber(freshCount) },
    { label: "Generated At", value: formatTime(generatedAt) },
  ];

  metrics.innerHTML = cards
    .map((card) => `<article class="metric-card"><div class="label">${card.label}</div><div class="value">${card.value}</div></article>`)
    .join("");
}

function renderMarketFilters(items) {
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
      renderMarketFilters(state.allItems);
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

function renderPeriodCards(item) {
  const entries = Object.entries(item.periods || {})
    .sort((a, b) => periodOrder(a[0]) - periodOrder(b[0]) || a[0].localeCompare(b[0]));

  if (!entries.length) {
    return '<div class="period-grid"><div class="period-card"><div class="period-head">-</div></div></div>';
  }

  return `<div class="period-grid">${entries
    .map(([period, detail]) => {
      const total = formatNumber(detail?.total_records || 0);
      const fetchTime = formatTime(detail?.last_fetch_time);
      const dataTime = formatTime(detail?.last_data_time);
      return `
        <article class="period-card">
          <div class="period-head">${period}</div>
          <div class="period-row"><span>records</span><strong>${total}</strong></div>
          <div class="period-row"><span>fetch</span><time>${fetchTime}</time></div>
          <div class="period-row"><span>data</span><time>${dataTime}</time></div>
        </article>`;
    })
    .join("")}</div>`;
}

function renderPeriodDetails(item) {
  const count = Object.keys(item.periods || {}).length;
  return `
    <details class="period-collapse">
      <summary><span>${count} periods</span><span class="caret"></span></summary>
      ${renderPeriodCards(item)}
    </details>`;
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
        <td>${formatNumber(item.total_records)}</td>
        <td>${formatTime(item.latest_fetch_time)}</td>
        <td>${formatTime(item.latest_data_time)}</td>
        <td>${renderPeriodDetails(item)}</td>
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
  renderMarketFilters(items);
  renderTable();

  document.getElementById("searchInput").addEventListener("input", (event) => {
    state.keyword = event.target.value;
    renderTable();
  });
}

init().catch((err) => {
  document.getElementById("tableBody").innerHTML = `
    <tr>
      <td colspan="7">Load failed: ${err.message}</td>
    </tr>
  `;
});
