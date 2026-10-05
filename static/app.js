// MARkit Dashboard Frontend Controller
let currentWatchlist = [];

function formatINR(val) {
  if (val === undefined || val === null || isNaN(val)) return "₹0.00";
  return "₹" + Number(val).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();

    // Clock and state
    document.getElementById("ist-clock").innerText = data.ist_time;
    const badge = document.getElementById("market-status-pill");
    const statusText = document.getElementById("market-status-text");

    badge.className = "market-status-badge ";
    if (data.market_state === "ACTIVE_MARKET") {
      badge.classList.add("status-active");
      statusText.innerText = "ACTIVE MARKET (09:15 - 15:15)";
    } else if (data.market_state === "AUTO_SQUAREOFF") {
      badge.classList.add("status-squareoff");
      statusText.innerText = "AUTO SQUARE-OFF (15:15 - 15:30)";
    } else {
      badge.classList.add("status-offhours");
      statusText.innerText = "OFF-HOURS RESEARCH";
    }

    // Circuit breaker state
    const cbText = document.getElementById("metric-circuit-breaker-status");
    if (data.circuit_breaker_triggered) {
      cbText.className = "metric-footer tag-negative";
      cbText.innerText = "CIRCUIT BREAKER TRIGGERED";
    } else {
      cbText.className = "metric-footer tag-positive";
      cbText.innerText = "Circuit Breaker Safe (<3.0%)";
    }

    // Gemini key rotator status
    const geminiBadge = document.getElementById("gemini-status-badge");
    if (geminiBadge) {
      if (data.gemini_keys_configured > 0) {
        geminiBadge.style.color = "var(--accent-green)";
        geminiBadge.style.background = "rgba(0, 229, 153, 0.12)";
        geminiBadge.style.borderColor = "rgba(0, 229, 153, 0.3)";
        geminiBadge.innerText = `Gemini AI: ${data.gemini_keys_configured} Key${data.gemini_keys_configured > 1 ? 's' : ''} (Random Rotation)`;
      } else {
        geminiBadge.style.color = "var(--text-dim)";
        geminiBadge.style.background = "rgba(255, 255, 255, 0.05)";
        geminiBadge.style.borderColor = "var(--border-color)";
        geminiBadge.innerText = "Gemini AI: 0 Keys (Heuristic Engine)";
      }
    }

    // Auto-pilot toggle button state
    const autoBtn = document.getElementById("btn-toggle-auto");
    if (autoBtn) {
      if (data.auto_trading_enabled) {
        autoBtn.innerHTML = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--accent-green);margin-right:6px;box-shadow:0 0 6px var(--accent-green);"></span>Auto-Pilot: Active`;
        autoBtn.style.borderColor = "rgba(0, 229, 153, 0.4)";
        autoBtn.style.color = "var(--accent-green)";
      } else {
        autoBtn.innerHTML = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--accent-yellow);margin-right:6px;"></span>Auto-Pilot: Paused`;
        autoBtn.style.borderColor = "rgba(245, 158, 11, 0.4)";
        autoBtn.style.color = "var(--accent-yellow)";
      }
    }

    // Simulation toggle button state
    const simBtn = document.getElementById("btn-toggle-sim");
    if (simBtn) {
      if (data.simulation_mode) {
        simBtn.innerHTML = `Mode: Simulation (Active)`;
        simBtn.style.borderColor = "rgba(6, 182, 212, 0.5)";
        simBtn.style.color = "var(--accent-cyan)";
      } else {
        simBtn.innerHTML = `Mode: Live NSE Clock`;
        simBtn.style.borderColor = "var(--border-color)";
        simBtn.style.color = "var(--text-muted)";
      }
    }

    // Max purchase limit on cash card
    const cashSub = document.getElementById("metric-cash-sub");
    if (cashSub && data.max_purchase_limit !== undefined) {
      cashSub.innerText = `Max Order Budget: ${formatINR(data.max_purchase_limit)}`;
    }
  } catch (e) {
    console.error("Error fetching status:", e);
  }
}

async function fetchPortfolio() {
  try {
    const res = await fetch("/api/portfolio");
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById("metric-equity").innerText = formatINR(data.total_equity);
    const returnPct = (((data.total_equity - data.initial_cash) / data.initial_cash) * 100).toFixed(2);
    const returnElem = document.getElementById("metric-equity-sub");
    returnElem.innerText = `${returnPct >= 0 ? "+" : ""}${returnPct}% Net Return`;
    returnElem.className = `metric-footer ${returnPct >= 0 ? "tag-positive" : "tag-negative"}`;

    document.getElementById("metric-cash").innerText = formatINR(data.cash_balance);
    document.getElementById("metric-realized-pnl").innerText = formatINR(data.realized_pnl);
    const rPnlElem = document.getElementById("metric-realized-sub");
    rPnlElem.className = `metric-footer ${data.realized_pnl >= 0 ? "tag-positive" : "tag-negative"}`;

    document.getElementById("metric-drawdown").innerText = `${data.daily_drawdown_pct.toFixed(2)}%`;

    // Holdings calculation
    const totalHoldingsValue = data.positions.reduce((acc, p) => acc + p.market_value, 0);
    const totalUnrealized = data.positions.reduce((acc, p) => acc + p.unrealized_pnl, 0);
    document.getElementById("metric-holdings-value").innerText = formatINR(totalHoldingsValue);
    document.getElementById("metric-holdings-count").innerText = `${data.positions.length} Positions`;
    const hSub = document.getElementById("metric-holdings-sub");
    hSub.innerText = `Unrealized: ${formatINR(totalUnrealized)}`;
    hSub.className = `metric-footer ${totalUnrealized >= 0 ? "tag-positive" : "tag-negative"}`;

    // Render positions table
    const posBody = document.getElementById("positions-body");
    document.getElementById("pos-count-badge").innerText = `${data.positions.length} Open`;

    if (data.positions.length === 0) {
      posBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-dim); padding: 20px;">No open positions currently held.</td></tr>`;
    } else {
      posBody.innerHTML = data.positions.map(p => `
        <tr>
          <td class="symbol-cell">${p.symbol}</td>
          <td style="font-family: 'JetBrains Mono';">${p.quantity}</td>
          <td style="font-family: 'JetBrains Mono';">${formatINR(p.average_entry_price)}</td>
          <td style="font-family: 'JetBrains Mono'; font-weight: 600;">${formatINR(p.current_price)}</td>
          <td style="font-family: 'JetBrains Mono';" class="${p.unrealized_pnl >= 0 ? "tag-positive" : "tag-negative"}">
            ${p.unrealized_pnl >= 0 ? "+" : ""}${formatINR(p.unrealized_pnl)} (${p.unrealized_pnl_pct}%)
          </td>
          <td style="font-size: 11px; color: var(--text-dim);">
            SL: ${p.stop_loss ? formatINR(p.stop_loss) : "--"} | TP: ${p.target ? formatINR(p.target) : "--"}
          </td>
        </tr>
      `).join("");
    }

    // Render trades table
    const tradesBody = document.getElementById("trades-body");
    if (data.trades.length === 0) {
      tradesBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 20px;">No trades executed yet.</td></tr>`;
    } else {
      tradesBody.innerHTML = data.trades.slice(0, 15).map(t => `
        <tr>
          <td style="font-family: 'JetBrains Mono'; font-size: 11px; color: var(--text-dim);">${t.trade_id}</td>
          <td><span class="thought-badge ${t.side === 'BUY' ? 'tag-positive' : 'tag-negative'}">${t.side}</span></td>
          <td class="symbol-cell">${t.symbol}</td>
          <td style="font-family: 'JetBrains Mono';">${t.quantity}</td>
          <td style="font-family: 'JetBrains Mono';">${formatINR(t.filled_price)}</td>
          <td style="font-size: 11px; color: var(--text-dim);">${formatINR(t.charges + t.slippage)}</td>
          <td style="font-family: 'JetBrains Mono';" class="${t.pnl > 0 ? "tag-positive" : t.pnl < 0 ? "tag-negative" : ""}">
            ${t.side === 'SELL' ? formatINR(t.pnl) : "--"}
          </td>
        </tr>
      `).join("");
    }
  } catch (e) {
    console.error("Error fetching portfolio:", e);
  }
}

async function loadWatchlist() {
  try {
    const res = await fetch("/api/watchlist");
    if (!res.ok) return;
    const data = await res.json();
    currentWatchlist = data.quotes;

    const tbody = document.getElementById("watchlist-body");
    tbody.innerHTML = data.quotes.map(q => `
      <tr>
        <td class="symbol-cell">
          <span>${q.symbol.replace(".NS", "")}</span>
          <span class="symbol-sub">NSE India</span>
        </td>
        <td class="price-cell">${formatINR(q.price)}</td>
        <td class="${q.change_pct >= 0 ? "tag-positive" : "tag-negative"}" style="font-family: 'JetBrains Mono';">
          ${q.change_pct >= 0 ? "+" : ""}${q.change_pct.toFixed(2)}%
        </td>
        <td style="font-size: 11px; color: var(--text-dim);">
          L: ${formatINR(q.day_low)} - H: ${formatINR(q.day_high)}
        </td>
        <td>
          <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="openOrderModal('${q.symbol}', ${q.price})">
            Trade
          </button>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    console.error("Error loading watchlist:", e);
  }
}

async function fetchThoughts() {
  try {
    const res = await fetch("/api/thoughts?limit=30");
    if (!res.ok) return;
    const data = await res.json();

    const consoleDiv = document.getElementById("thought-console");
    if (data.thoughts.length > 0) {
      consoleDiv.innerHTML = data.thoughts.map(t => {
        const timeStr = t.timestamp.split("T")[1]?.slice(0, 8) || "";
        return `
          <div class="thought-entry action-${t.action}">
            <div class="thought-header">
              <span class="thought-badge">${t.action}</span>
              <span>${timeStr} IST</span>
            </div>
            <div class="thought-body">${t.thought}</div>
          </div>
        `;
      }).reverse().join("");
    }
  } catch (e) {
    console.error("Error fetching thoughts:", e);
  }
}

async function fetchResearch() {
  try {
    const res = await fetch("/api/research");
    if (!res.ok) return;
    const data = await res.json();
    const container = document.getElementById("research-container");

    let html = "";
    if (data.macro_headlines && data.macro_headlines.length > 0) {
      html += `<div style="font-size: 11px; font-weight: 600; color: var(--text-dim); text-transform: uppercase;">Economic Times Indian Market Headlines</div>`;
      html += data.macro_headlines.map(h => `
        <div class="news-item">
          <div class="news-title">${h}</div>
          <div class="news-meta">
            <span>Economic Times</span>
            <span class="thought-badge">Macro</span>
          </div>
        </div>
      `).join("");
    }

    if (data.watchlist_sentiment) {
      html += `<div style="font-size: 11px; font-weight: 600; color: var(--text-dim); text-transform: uppercase; margin-top: 12px;">Watchlist Sentiment Ratings</div>`;
      for (const [sym, info] of Object.entries(data.watchlist_sentiment)) {
        html += `
          <div class="news-item">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 600;">${sym}</span>
              <span class="brand-badge ${info.rating === 'BULLISH' ? 'tag-positive' : info.rating === 'BEARISH' ? 'tag-negative' : ''}">${info.rating} (${info.sentiment})</span>
            </div>
            <div class="news-title" style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">${info.headline}</div>
          </div>
        `;
      }
    }

    container.innerHTML = html || `<div style="color: var(--text-dim); text-align: center; padding: 20px;">No research items currently cached.</div>`;
  } catch (e) {
    console.error("Error fetching research:", e);
  }
}

async function toggleAutoTrade() {
  try {
    await fetch("/api/auto-trade/toggle", { method: "POST" });
    await fetchStatus();
    await fetchThoughts();
  } catch (e) {
    console.error("Error toggling auto-pilot:", e);
  }
}

async function toggleSimulationMode() {
  try {
    await fetch("/api/simulation-mode/toggle", { method: "POST" });
    await fetchStatus();
    await fetchThoughts();
  } catch (e) {
    console.error("Error toggling simulation mode:", e);
  }
}

async function triggerCycle() {
  const btn = document.getElementById("btn-trigger-cycle");
  const origText = btn.innerHTML;
  btn.innerHTML = "Thinking...";
  btn.disabled = true;

  try {
    const res = await fetch("/api/trigger-cycle", { method: "POST" });
    const data = await res.json();
    await Promise.all([fetchStatus(), fetchPortfolio(), fetchThoughts(), fetchResearch()]);
  } catch (e) {
    console.error("Error triggering cycle:", e);
  } finally {
    btn.innerHTML = origText;
    btn.disabled = false;
  }
}

async function emergencySquareOff() {
  if (!confirm("Are you sure you want to square off all open positions immediately?")) return;
  try {
    const res = await fetch("/api/square-off-all", { method: "POST" });
    await fetchPortfolio();
    await fetchThoughts();
  } catch (e) {
    console.error("Error squaring off all:", e);
  }
}

function openOrderModal(symbol, price) {
  document.getElementById("order-symbol").value = symbol;
  document.getElementById("order-price").value = formatINR(price);
  document.getElementById("order-modal").classList.add("active");
}

function closeOrderModal() {
  document.getElementById("order-modal").classList.remove("active");
}

async function submitOrder() {
  const symbol = document.getElementById("order-symbol").value;
  const side = document.getElementById("order-side").value;
  const quantity = parseInt(document.getElementById("order-qty").value, 10);

  try {
    const res = await fetch("/api/order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, side, quantity })
    });
    const data = await res.json();
    if (!res.ok) {
      alert("Order Rejected: " + (data.detail || data.message));
    } else {
      closeOrderModal();
      await fetchPortfolio();
      await fetchThoughts();
    }
  } catch (e) {
    alert("Error submitting order: " + e.message);
  }
}

// Daily Report Modal Controller
function openReportModal() {
  const modal = document.getElementById("report-modal");
  if (modal) {
    modal.classList.add("active");
    loadDailyReportData();
  }
}

function closeReportModal() {
  const modal = document.getElementById("report-modal");
  if (modal) {
    modal.classList.remove("active");
  }
}

async function loadDailyReportData() {
  try {
    // 1. Fetch current daily report metrics & trades
    const res = await fetch("/api/reports/daily");
    if (res.ok) {
      const data = await res.json();
      document.getElementById("report-date-badge").innerText = data.date || "Today";
      document.getElementById("rep-initial-amount").innerText = formatINR(data.initial_amount);
      document.getElementById("rep-final-amount").innerText = formatINR(data.final_amount);
      document.getElementById("rep-total-trades").innerText = data.total_trades;
      document.getElementById("rep-trades-breakdown").innerText = `${data.buy_trades} BUY / ${data.sell_trades} SELL (${data.win_rate_pct}% Win)`;
      document.getElementById("rep-gross-profit").innerText = formatINR(data.profit);
      document.getElementById("rep-gross-loss").innerText = formatINR(data.loss);

      const netPnlEl = document.getElementById("rep-net-pnl");
      const sign = data.net_pnl > 0 ? "+" : "";
      netPnlEl.innerText = `${sign}${formatINR(data.net_pnl)}`;
      netPnlEl.className = "report-kpi-value " + (data.net_pnl > 0 ? "tag-positive" : data.net_pnl < 0 ? "tag-negative" : "tag-neutral");

      const retSign = data.net_return_pct > 0 ? "+" : "";
      document.getElementById("rep-net-return").innerText = `${retSign}${data.net_return_pct.toFixed(2)}% Return`;

      const slipBadge = document.getElementById("rep-charges-slip-badge");
      if (slipBadge) {
        slipBadge.innerText = `Charges: ${formatINR(data.total_charges)} | Slippage: ${formatINR(data.total_slippage)}`;
      }

      // Render daily trades table
      const tbody = document.getElementById("rep-trades-table-body");
      if (tbody) {
        if (!data.trades || data.trades.length === 0) {
          tbody.innerHTML = '<tr><td colspan="12" style="text-align: center; color: var(--text-dim); padding: 20px;">No trades recorded for this date.</td></tr>';
        } else {
          tbody.innerHTML = data.trades.map(t => {
            const timeStr = t.timestamp.includes("T") ? t.timestamp.split("T")[1].substring(0, 8) : t.timestamp;
            const pnlStr = t.side === "SELL" ? (t.pnl >= 0 ? `+${formatINR(t.pnl)}` : `-${formatINR(Math.abs(t.pnl))}`) : "—";
            const pnlClass = t.side === "SELL" ? (t.pnl >= 0 ? "tag-positive" : "tag-negative") : "";
            const sideClass = t.side === "BUY" ? "tag-buy" : "tag-sell";

            return `<tr>
              <td><code>${t.trade_id}</code></td>
              <td style="color: var(--text-dim);">${timeStr}</td>
              <td style="font-weight: 600; color: var(--text-bright);">${t.symbol}</td>
              <td><span class="${sideClass}">${t.side}</span></td>
              <td>${t.quantity}</td>
              <td>${formatINR(t.requested_price)}</td>
              <td>${formatINR(t.filled_price)}</td>
              <td>${formatINR(t.slippage)}</td>
              <td>${formatINR(t.charges)}</td>
              <td>${formatINR(t.net_amount)}</td>
              <td class="${pnlClass}">${pnlStr}</td>
              <td style="font-size: 11px; color: var(--text-dim); max-width: 200px; white-space: normal;">${t.reason || "Executed"}</td>
            </tr>`;
          }).join("");
        }
      }
    }

    // 2. Fetch master summary document content
    const docRes = await fetch("/api/reports/summary-document");
    if (docRes.ok) {
      const docData = await docRes.json();
      const preEl = document.getElementById("rep-master-doc-content");
      if (preEl) {
        preEl.innerText = docData.content || "Empty master document.";
      }
    }
  } catch (e) {
    console.error("Error loading daily report data:", e);
  }
}

async function triggerReportGeneration() {
  const btn = event?.currentTarget;
  if (btn) {
    btn.disabled = true;
    btn.innerText = "Generating...";
  }
  try {
    const res = await fetch("/api/reports/generate", { method: "POST" });
    if (res.ok) {
      await loadDailyReportData();
      await fetchThoughts();
    }
  } catch (e) {
    alert("Error generating report: " + e.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg> Generate / Refresh Report`;
    }
  }
}

// Mobile View Tab Switcher
let activeMobileTab = "all";

function switchMobileTab(tab) {
  activeMobileTab = tab;
  document.querySelectorAll(".mobile-tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-tab") === tab);
  });
  applyMobileTabVisibility();
}

function applyMobileTabVisibility() {
  const isMobile = window.innerWidth <= 991;
  const cards = document.querySelectorAll(".dashboard-col .card");
  
  if (!isMobile) {
    cards.forEach(c => c.style.display = "");
    const colMarket = document.getElementById("col-market");
    const colIntel = document.getElementById("col-intel");
    if (colMarket) colMarket.style.display = "";
    if (colIntel) colIntel.style.display = "";
    return;
  }

  cards.forEach(card => {
    const cat = card.getAttribute("data-category");
    if (activeMobileTab === "all" || cat === activeMobileTab) {
      card.style.display = "flex";
    } else {
      card.style.display = "none";
    }
  });

  ["col-market", "col-intel"].forEach(colId => {
    const col = document.getElementById(colId);
    if (!col) return;
    const hasVisibleCard = Array.from(col.querySelectorAll(".card")).some(c => c.style.display !== "none");
    col.style.display = hasVisibleCard ? "flex" : "none";
  });
}

window.addEventListener("resize", applyMobileTabVisibility);

// Initial boot & recurring polls
window.addEventListener("DOMContentLoaded", () => {
  fetchStatus();
  fetchPortfolio();
  loadWatchlist();
  fetchThoughts();
  fetchResearch();
  applyMobileTabVisibility();

  // Poll status & thoughts every 4 seconds
  setInterval(fetchStatus, 4000);
  setInterval(fetchPortfolio, 4000);
  setInterval(fetchThoughts, 5000);
  setInterval(loadWatchlist, 15000);
});
