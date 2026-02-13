const headers = {
  "Content-Type": "application/json",
  "x-tenant-id": "demo-tenant",
  "x-user-id": "demo-user",
  "x-user-role": "owner",
};

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { ...headers, ...(options.headers || {}) },
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail));
  }
  return res.json();
}

function statusBadge(status) {
  return `<span class="badge ${status}">${status.toUpperCase()}</span>`;
}

function connectorText(connector) {
  return `${connector.supplierName} · ${connector.status} · poll ${connector.pollIntervalMinutes}m`;
}

async function loadConnectors() {
  const data = await api("/api/integrations/suppliers");
  const list = document.getElementById("connectors");
  const select = document.getElementById("sync-connector");
  list.innerHTML = "";
  select.innerHTML = "";

  data.items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = connectorText(item);
    list.appendChild(li);

    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = `${item.supplierName} (${item.status})`;
    select.appendChild(opt);
  });
}

async function loadSummary() {
  const summary = await api("/api/dashboard/summary");
  document.getElementById("red-count").textContent = summary.redCount;
  document.getElementById("yellow-count").textContent = summary.yellowCount;
  document.getElementById("green-count").textContent = summary.greenCount;
  document.getElementById("open-alerts").textContent = summary.openAlerts;
  const syncText = summary.lastSyncAt
    ? `${summary.syncHealth} · last sync ${new Date(summary.lastSyncAt).toLocaleString()}`
    : summary.syncHealth;
  document.getElementById("sync-health").textContent = `Sync: ${syncText}`;
}

async function loadOrders() {
  const data = await api("/api/orders/risk?pageSize=100");
  const body = document.getElementById("orders-body");
  body.innerHTML = "";

  if (!data.items.length) {
    body.innerHTML = '<tr><td colspan="7">No scored open orders yet. Run sync to generate data.</td></tr>';
    return;
  }

  data.items.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${statusBadge(item.status)}</td>
      <td>${item.projectId}</td>
      <td>${item.supplierOrderId}</td>
      <td>${item.materialName}</td>
      <td>${item.etaDate}</td>
      <td>${item.riskScore.toFixed(2)}</td>
      <td>${item.reasonCodes.join(", ")}</td>
    `;
    body.appendChild(tr);
  });
}

async function loadAlerts() {
  const data = await api("/api/alerts?status=open");
  const list = document.getElementById("alerts");
  list.innerHTML = "";

  if (!data.items.length) {
    list.innerHTML = "<li>No open alerts.</li>";
    return;
  }

  data.items.forEach((alert) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <strong>[${alert.severity.toUpperCase()}]</strong> ${alert.message}<br/>
      Actions: ${alert.recommendations.join(" | ")}
    `;
    list.appendChild(li);
  });
}

async function refreshAll() {
  await loadConnectors();
  await loadSummary();
  await loadOrders();
  await loadAlerts();
}

document.getElementById("connector-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const supplierName = document.getElementById("supplier-name").value;
  const apiKey = document.getElementById("api-key").value;
  try {
    await api("/api/integrations/suppliers", {
      method: "POST",
      body: JSON.stringify({
        supplierName,
        authType: "api_key",
        credentials: { apiKey },
        pollIntervalMinutes: 1440,
      }),
    });
    document.getElementById("api-key").value = "";
    await refreshAll();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("run-sync-btn").addEventListener("click", async () => {
  const connectorId = document.getElementById("sync-connector").value;
  if (!connectorId) {
    alert("Create a connector first.");
    return;
  }

  try {
    const out = await api("/api/sync/run", {
      method: "POST",
      body: JSON.stringify({ connectorId, mode: "incremental" }),
    });
    document.getElementById("sync-output").textContent = JSON.stringify(out, null, 2);
    await refreshAll();
  } catch (err) {
    alert(err.message);
  }
});

refreshAll().catch((err) => {
  console.error(err);
});
