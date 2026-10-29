const $ = (id) => document.getElementById(id);

const SAMPLES = [
  { label: "⚡ Electricity bill", text: "Dear Consumer, your electricity power will be disconnected tonight at 9.30pm from electricity office because your previous month bill was not updated. Please immediately contact our electricity officer 8250947146. Thank you." },
  { label: "🏦 Bank KYC link", text: "Dear SBI user, your YONO account will be blocked today due to incomplete KYC. Update your PAN immediately: http://sbi-yono-kyc.xyz/update to avoid suspension. -SBI" },
  { label: "💼 Part-time job", text: "Hello! I am Priya from HR team. We are hiring part time work from home. Just like YouTube videos and earn Rs 3000-8000 daily. No experience needed. Contact on Telegram @priya_hr_task for details." },
  { label: "👮 Digital arrest", text: "This is Inspector Sharma from Mumbai Cyber Cell. A FedEx parcel in your name containing illegal drugs was seized by customs. A money laundering case is registered against you. Join the video call immediately or a digital arrest warrant will be issued." },
  { label: "✅ Genuine OTP", text: "482913 is your OTP for a transaction of INR 2,450.00 at AMAZON on your HDFC Bank Credit Card ending 4321. Valid for 10 mins. Do not share this OTP with anyone. -HDFC Bank" },
  { label: "📦 Delivery update", text: "Your Amazon order #407-2931847-1123 with 'Prestige Pressure Cooker 5L' has been delivered. Track or return at amazon.in/your-orders" },
];

const AGENT_CLASS = (a = "") => (a.includes("Tavily") ? "tavily" : a.includes("Rule") ? "rules" : "");
let imageData = null;
let busy = false;

// ---------- setup ----------
for (const s of SAMPLES) {
  const b = document.createElement("button");
  b.className = "chip";
  b.type = "button";
  b.textContent = s.label;
  b.onclick = () => { $("msg").value = s.text; $("msg").focus(); };
  $("sampleList").appendChild(b);
}

try {
  const saved = JSON.parse(localStorage.getItem("ss-prefs") || "{}");
  if (saved.lang) $("lang").value = saved.lang;
  if (saved.region) $("region").value = saved.region;
} catch {}
const savePrefs = () => { try { localStorage.setItem("ss-prefs", JSON.stringify({ lang: $("lang").value, region: $("region").value })); } catch {} };
$("lang").onchange = savePrefs;
$("region").onchange = savePrefs;

fetch("/api/health").then((r) => r.json()).then((h) => {
  if (h.mock || !h.nebius) {
    $("banner").hidden = false;
    $("banner").textContent = "Demo mode: Nebius Token Factory key not configured, so AI steps return placeholder output.";
  } else if (!h.tavily) {
    $("banner").hidden = false;
    $("banner").textContent = "Web investigation is off: Tavily key not configured.";
  }
}).catch(() => {});

// Shareable links: /?try=2 runs the third example on load.
const tryIdx = Number(new URLSearchParams(location.search).get("try"));
if (Number.isInteger(tryIdx) && SAMPLES[tryIdx] && new URLSearchParams(location.search).has("try")) {
  $("msg").value = SAMPLES[tryIdx].text;
  setTimeout(analyze, 300);
}

// ---------- screenshot handling ----------
const drop = $("drop");
drop.onclick = (e) => { if (e.target.id !== "clearImg") $("file").click(); };
drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("file").click(); } };
$("file").onchange = (e) => e.target.files[0] && loadImage(e.target.files[0]);
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) loadImage(f); };
document.addEventListener("paste", (e) => {
  const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
  if (item) loadImage(item.getAsFile());
});
$("clearImg").onclick = (e) => { e.stopPropagation(); imageData = null; $("preview").hidden = true; $("dropText").hidden = false; $("file").value = ""; };

function loadImage(file) {
  if (!file.type.startsWith("image/")) return;
  const img = new Image();
  img.onload = () => {
    const scale = Math.min(1, 1600 / Math.max(img.width, img.height));
    const c = document.createElement("canvas");
    c.width = Math.round(img.width * scale);
    c.height = Math.round(img.height * scale);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    imageData = c.toDataURL("image/jpeg", 0.85);
    $("previewImg").src = imageData;
    $("preview").hidden = false;
    $("dropText").hidden = true;
    URL.revokeObjectURL(img.src);
  };
  img.src = URL.createObjectURL(file);
}

// ---------- analysis ----------
$("go").onclick = analyze;
$("msg").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) analyze(); });

async function analyze() {
  if (busy) return;
  const text = $("msg").value.trim();
  if (!text && !imageData) { $("msg").focus(); return; }
  busy = true;
  resetOutput();
  $("go").disabled = true;
  $("go").querySelector(".btn-label").textContent = "Investigating…";

  try {
    const resp = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, image: imageData, language: $("lang").value, region: $("region").value }),
    });
    if (!resp.ok || !resp.body) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || `Server error ${resp.status}`);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        if (chunk.startsWith("data: ")) handle(JSON.parse(chunk.slice(6)));
      }
    }
  } catch (err) {
    showError(err.message || String(err));
  } finally {
    busy = false;
    $("go").disabled = false;
    $("go").querySelector(".btn-label").textContent = "Check this message";
  }
}

function resetOutput() {
  $("empty").hidden = true;
  $("trace").hidden = false;
  $("result").hidden = true;
  $("error").hidden = true;
  $("familyCard").hidden = true;
  $("steps").replaceChildren();
  $("totalTime").textContent = "";
}

function handle(ev) {
  switch (ev.type) {
    case "step": return renderStep(ev);
    case "verdict": return renderVerdict(ev);
    case "family": return renderFamily(ev);
    case "done": $("totalTime").textContent = `· ${(ev.total_ms / 1000).toFixed(1)}s`; return;
    case "error": return showError(ev.message);
  }
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function renderStep(ev) {
  let li = document.querySelector(`.step[data-id="${ev.id}"]`);
  if (!li) {
    li = el("li", "step");
    li.dataset.id = ev.id;
    $("steps").appendChild(li);
  }
  li.className = `step ${ev.status}`;
  li.replaceChildren();
  const title = el("div", "step-title", ev.title);
  const agent = ev.agent || li.dataset.agent;
  if (ev.agent) li.dataset.agent = ev.agent;
  if (agent) title.appendChild(el("span", `agent ${AGENT_CLASS(agent)}`, agent));
  if (ev.ms) title.appendChild(el("span", "ms", `${(ev.ms / 1000).toFixed(1)}s`));
  li.appendChild(title);
  if (ev.model) li.appendChild(el("div", "step-model", ev.model));
  if (ev.detail) li.appendChild(el("div", "step-detail", ev.detail));
}

function renderVerdict(v) {
  $("result").hidden = false;
  const labels = { SCAM: "Scam", SUSPICIOUS: "Suspicious", LIKELY_SAFE: "Likely safe" };
  $("verdictCard").className = `verdict ${v.verdict}`;
  $("verdictLabel").textContent = labels[v.verdict] || v.verdict;
  $("headline").textContent = v.headline || "";
  $("scamType").textContent = [v.scam_type && v.scam_type !== "none" ? v.scam_type : "", v.confidence ? `${v.confidence} confidence` : ""].filter(Boolean).join(" · ");
  animateScore(v.risk_score);
  $("guardrail").hidden = !v.guardrail;
  $("guardrail").textContent = v.guardrail ? `🛡️ Safety check: ${v.guardrail}` : "";

  const evIds = new Set((v.evidence || []).map((e) => e.id));
  const flags = $("flags");
  flags.replaceChildren();
  (v.red_flags || []).forEach((f) => {
    const li = el("li");
    const b = el("b", null, f.flag);
    (f.evidence || []).filter((id) => evIds.has(id)).forEach((id) => {
      const a = el("a", "ev", id);
      a.href = `#ev-${id}`;
      a.onclick = () => { document.querySelector(".evidence").open = true; };
      b.appendChild(a);
    });
    li.append(b, el("span", null, f.why || ""));
    flags.appendChild(li);
  });
  if (!flags.children.length) flags.appendChild(el("li", null, "No red flags found."));

  fillList("safe", v.safe_signs);
  $("safeWrap").hidden = !(v.safe_signs || []).length;
  fillList("todo", v.what_to_do);
  fillList("dont", v.do_not);
  $("officialWrap").hidden = !v.official_channel;
  $("official").textContent = v.official_channel || "";
  fillList("help", v.helplines);
  $("helpWrap").hidden = !(v.helplines || []).length;

  const evList = $("evidence");
  evList.replaceChildren();
  (v.evidence || []).forEach((e) => {
    const li = el("li");
    li.id = `ev-${e.id}`;
    li.appendChild(el("div", "purpose", `${e.id} · ${e.purpose}`));
    const safeUrl = /^https?:\/\//i.test(e.url) ? e.url : null;
    const a = el(safeUrl ? "a" : "span", null, e.title || e.url);
    if (safeUrl) { a.href = safeUrl; a.target = "_blank"; a.rel = "noopener noreferrer"; }
    li.append(a, el("p", null, e.snippet));
    evList.appendChild(li);
  });
  $("evCount").textContent = (v.evidence || []).length;
  $("verdictCard").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderFamily(f) {
  $("familyCard").hidden = false;
  $("familyLang").textContent = f.language;
  $("familyText").textContent = f.explanation || "";
  $("shareText").textContent = f.share_text || "";
  $("waShare").href = `https://wa.me/?text=${encodeURIComponent(f.share_text || "")}`;
  $("copyShare").onclick = async () => {
    try { await navigator.clipboard.writeText(f.share_text || ""); $("copyShare").textContent = "Copied ✓"; } catch { $("copyShare").textContent = "Copy failed"; }
    setTimeout(() => ($("copyShare").textContent = "Copy"), 1500);
  };
}

function fillList(id, items) {
  const ul = $(id);
  ul.replaceChildren();
  (items || []).forEach((t) => ul.appendChild(el("li", null, t)));
}

function animateScore(target) {
  const n = Math.max(0, Math.min(100, Number(target) || 0));
  $("gaugeArc").style.strokeDashoffset = 157 - (157 * n) / 100;
  const start = performance.now();
  const tick = (t) => {
    const p = Math.min(1, (t - start) / 900);
    $("score").textContent = Math.round(n * (1 - Math.pow(1 - p, 3)));
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function showError(msg) {
  $("error").hidden = false;
  $("error").textContent = `Something went wrong: ${msg}`;
}
