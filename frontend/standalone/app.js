/* AI Crop Recommendation System - vanilla JS, no frameworks. */
"use strict";

var META = null;
var FARMERS = [];          // [{farmer_id, farmer_name}]
var NAME_TO_ID = {};
var LAST_REQUEST = null;
var OUTCOME = "profit";
var SELECTED_FARMER_ID = "";

function $(id) { return document.getElementById(id); }

function fmtINR(n) {
  return "Rs " + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

// ---------------- API ----------------
function api(path, opts) {
  return fetch(path, opts).then(function (r) {
    if (!r.ok) throw new Error("API error " + r.status);
    return r.json();
  });
}

// ---------------- init ----------------
window.addEventListener("DOMContentLoaded", function () {
  api("/api/farmers").then(function (list) {
    FARMERS = list;
    list.forEach(function (f) { NAME_TO_ID[f.farmer_name.toLowerCase()] = f.farmer_id; });
  }).catch(function () {});

  api("/api/meta").then(function (meta) {
    META = meta;
    $("loading-note").style.display = "none";
    $("form-section").style.display = "";
    var stateSel = $("state");
    Object.keys(meta.states).sort().forEach(function (s) {
      var o = document.createElement("option"); o.value = s; o.textContent = s;
      stateSel.appendChild(o);
    });
    meta.soil_types.forEach(function (t) {
      var o = document.createElement("option"); o.value = t; o.textContent = t;
      $("soilType").appendChild(o);
    });

    // outcome toggle
    function paintToggle() {
      $("btnProfit").className = OUTCOME === "profit" ? "on-profit" : "";
      $("btnLoss").className = OUTCOME === "loss" ? "on-loss" : "";
    }
    $("btnProfit").onclick = function () { OUTCOME = "profit"; paintToggle(); };
    $("btnLoss").onclick = function () { OUTCOME = "loss"; paintToggle(); };
    paintToggle();

    // previous-crop search
    $("prevCrop").addEventListener("input", function (e) {
      showCropMatches(e.target.value);
    });

    // farmer name autocomplete
    $("farmerId").addEventListener("input", function (e) {
      showFarmerMatches(e.target.value);
    });
    $("farmerId").addEventListener("blur", function () {
      setTimeout(function () { $("farmerList").innerHTML = ""; }, 300);
    });
  }).catch(function () {
    $("loading-note").innerHTML =
      '<span class="err">Could not reach the backend. Start it with: ' +
      '<code>python -m uvicorn backend.main:app --port 8000</code></span>';
  });
});

function showCropMatches(q) {
  var box = $("cropList");
  if (!q || PREV_CROP_LOCKED()) { box.innerHTML = ""; return; }
  var matches = META.crops.map(function (c) { return c.crop_name; })
    .filter(function (c) { return c.toLowerCase().indexOf(q.toLowerCase()) !== -1; })
    .slice(0, 8);
  box.innerHTML = "";
  box.style.cssText =
    "position:absolute;z-index:10;background:#fff;border:1px solid #e5e7eb;" +
    "border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,.15);width:100%;max-height:190px;overflow:auto";
  matches.forEach(function (c) {
    var b = document.createElement("button");
    b.type = "button"; b.textContent = c;
    b.style.cssText = "display:block;width:100%;text-align:left;padding:8px 12px;border:0;background:#fff;cursor:pointer;font-size:14px";
    b.onmouseover = function () { b.style.background = "#f0fdf4"; };
    b.onmouseout = function () { b.style.background = "#fff"; };
    b.onmousedown = function (e) {
      e.preventDefault();
      $("prevCrop").value = c;
      box.innerHTML = "";
    };
    box.appendChild(b);
  });
}
function PREV_CROP_LOCKED() { return false; }

function showFarmerMatches(q) {
  var box = $("farmerList");
  SELECTED_FARMER_ID = "";   // reset until a known name is picked or submit resolves
  if (!q) { box.innerHTML = ""; return; }
  var ql = q.toLowerCase();
  var matches = FARMERS.filter(function (f) {
    return f.farmer_name.toLowerCase().indexOf(ql) !== -1;
  }).slice(0, 8);
  box.innerHTML = "";
  if (!matches.length) { return; }
  box.style.cssText =
    "position:absolute;z-index:10;background:#fff;border:1px solid #e5e7eb;" +
    "border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,.15);width:100%;max-height:190px;overflow:auto";
  matches.forEach(function (f) {
    var b = document.createElement("button");
    b.type = "button"; b.textContent = f.farmer_name + " (" + f.farmer_id + ")";
    b.style.cssText = "display:block;width:100%;text-align:left;padding:8px 12px;border:0;background:#fff;cursor:pointer;font-size:14px";
    b.onmouseover = function () { b.style.background = "#f0fdf4"; };
    b.onmouseout = function () { b.style.background = "#fff"; };
    // mousedown fires BEFORE the input's blur wipes the dropdown - use it,
    // not click, or the selection is lost.
    b.onmousedown = function (e) {
      e.preventDefault();          // keep focus on the input
      $("farmerId").value = f.farmer_name;
      SELECTED_FARMER_ID = f.farmer_id;
      box.innerHTML = "";
    };
    box.appendChild(b);
  });
}

document.addEventListener("change", function (e) {
  if (e.target.id === "state") {
    var dsel = $("district");
    dsel.innerHTML = '<option value="">Select district...</option>';
    (META.states[e.target.value] || []).forEach(function (d) {
      var o = document.createElement("option"); o.value = d.district; o.textContent = d.district;
      dsel.appendChild(o);
    });
  }
  if (e.target.id === "district") {
    var st = $("state").value;
    var entry = (META.states[st] || []).filter(function (x) { return x.district === e.target.value; })[0];
    if (entry) { $("soilType").value = entry.soil_type; $("soilHint").textContent = "(auto-set)"; }
  }
});

// ---------------- recommend ----------------
$("form").addEventListener("submit", function (e) {
  e.preventDefault();
  var btn = $("submitBtn");
  btn.disabled = true; btn.textContent = "Analyzing..."; $("formErr").innerHTML = "";
  var typedName = $("farmerId").value.trim();
  var farmerId = SELECTED_FARMER_ID || NAME_TO_ID[typedName.toLowerCase()];
  var farmerName = null;
  if (!farmerId) {
    // brand-new farmer: use the typed name as their identity
    farmerName = typedName || "New Farmer";
    farmerId = "U-" + farmerName.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  }
  var payload = {
    farmer_id: farmerId,
    soil_type: $("soilType").value,
    state: $("state").value,
    district: $("district").value,
    previous_crop: $("prevCrop").value,
    previous_outcome: OUTCOME,
  };
  if ($("amount").value !== "") payload.previous_profit_amount = Number($("amount").value);
  payload.farmer_name = farmerName;
  LAST_REQUEST = { payload: payload, name: farmerName };

  api("/api/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(function (data) {
    renderResults(data);
    // auto-load this farmer's history below
    $("histId").value = farmerName || $("farmerId").value.trim();
    loadHistory(payload.farmer_id);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }).catch(function (err) {
    $("formErr").innerHTML = '<div class="err">' + err.message + "</div>";
  }).finally(function () {
    btn.disabled = false; btn.textContent = "Get Top-3 Crop Recommendations";
  });
});

function renderResults(data) {
  $("results-section").style.display = "";
  $("resultsTime").textContent = new Date(data.generated_at).toLocaleString();
  var medals = [
    { cls: "r1", label: "#1 Best Choice" },
    { cls: "r2", label: "#2" },
    { cls: "r3", label: "#3" },
  ];
  var wrap = $("resultsCards");
  wrap.innerHTML = "";
  data.recommendations.forEach(function (rec) {
    var i = Math.min(rec.rank - 1, 2);
    var m = medals[i];
    var card = document.createElement("div");
    card.className = "card " + m.cls;
    card.innerHTML =
      '<div class="bar">' + m.label + "</div>" +
      '<div class="inner">' +
        '<div class="row-between">' +
          '<div class="crop-name"></div>' +
          '<div class="profit"><span class="pval"></span><small>net profit / acre</small></div>' +
        "</div>" +
        '<button type="button" class="why-btn">Why this crop?</button>' +
        '<div class="details" style="display:none">' +
          '<div class="reason"></div>' +
          '<div class="stats">' +
            "<div><span>YIELD</span><b></b></div>" +
            "<div><span>PRICE</span><b></b></div>" +
            "<div><span>COST</span><b></b></div>" +
          "</div>" +
        "</div>" +
      "</div>";
    card.querySelector(".crop-name").textContent = rec.crop_name;
    var pv = card.querySelector(".pval");
    pv.textContent = fmtINR(rec.predicted_profit_rs_per_acre);
    pv.style.color = rec.predicted_profit_rs_per_acre >= 0 ? "#15803d" : "#dc2626";
    card.querySelector(".reason").textContent = rec.reason;
    var stats = card.querySelectorAll(".stats b");
    stats[0].textContent = rec.predicted_yield_ton_per_acre.toFixed(2) + " t/ac";
    stats[1].textContent = fmtINR(Math.round(rec.predicted_price_rs_per_quintal)) + "/qtl";
    stats[2].textContent = fmtINR(rec.cost_of_cultivation_rs_per_acre);
    card.querySelector(".why-btn").onclick = function () {
      var d = card.querySelector(".details");
      d.style.display = d.style.display === "none" ? "" : "none";
    };
    wrap.appendChild(card);
  });
}

// ---------------- history ----------------
function loadHistory(fid) {
  if (!fid) return;
  $("historyBody").innerHTML = '<span class="muted">Loading...</span>';
  $("logBtn").style.display = LAST_REQUEST ? "" : "none";
  api("/api/history/" + encodeURIComponent(fid)).then(function (rows) {
    if (!rows.length) {
      $("historyBody").innerHTML = '<span class="muted">No history found for ' + fid + ".</span>";
      return;
    }
    var html = '<div style="overflow-x:auto"><table><thead><tr>' +
      ["Year", "Season", "Soil", "Prev crop", "Crop sown", "Outcome", "Profit Rs/acre"]
        .map(function (t) { return "<th>" + t + "</th>"; }).join("") +
      "</tr></thead><tbody>";
    rows.forEach(function (r) {
      html += "<tr><td>" + r.year + "</td><td>" + r.season + "</td><td>" + r.soil_type +
        "</td><td>" + (r.previous_crop || "-") + "</td><td><b>" + r.next_crop_sown + "</b></td>" +
        '<td><span class="pill ' + r.outcome + '">' + r.outcome + "</span></td>" +
        "<td>" + (r.profit_amount_rs_per_acre != null ? Math.round(r.profit_amount_rs_per_acre).toLocaleString("en-IN") : "-") + "</td></tr>";
    });
    $("historyBody").innerHTML = html + "</tbody></table></div>";
  }).catch(function (err) {
    $("historyBody").innerHTML = '<span class="err">' + err.message + "</span>";
  });
}

function logThisSeason() {
  if (!LAST_REQUEST) return;
  var req = LAST_REQUEST.payload;
  var fid = $("histId").value.trim() || req.farmer_id;
  api("/api/history", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      farmer_id: fid,
      farmer_name: LAST_REQUEST.name,
      season: "Kharif", year: new Date().getFullYear(),
      soil_type: req.soil_type,
      previous_crop: req.previous_crop,
      outcome: req.previous_outcome,
      profit_amount_rs_per_acre: req.previous_profit_amount != null ? req.previous_profit_amount : null,
      next_crop_sown: "",
    }),
  }).then(function (logged) {
    $("logBtn").textContent = "Logged";
    loadHistory(fid);
  }).catch(function (err) {
    $("historyBody").innerHTML = '<span class="err">' + err.message + "</span>";
  });
}
