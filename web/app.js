const $ = (s) => document.querySelector(s);
const state = { lang: localStorage.getItem('se.lang') || 'en', voice: false, cam: 'cam-1', cams: [], msgs: null, charts: {} };
const TYPE_COLORS = { no_helmet: '#FF4D4F', no_vest: '#FFC21A', zone: '#4DA3FF', fall: '#B05CFF' };

function t(type) { return state.msgs?.[state.lang]?.[type] || state.msgs?.en?.[type] || { title: type, say: type }; }
function timeStr(ts) { return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }

// ---------- header ----------
setInterval(() => ($('#clock').textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })), 1000);
document.querySelectorAll('#lang button').forEach((b) => {
  if (b.dataset.l === state.lang) { document.querySelectorAll('#lang button').forEach((x) => x.classList.remove('on')); b.classList.add('on'); }
  b.onclick = () => {
    state.lang = b.dataset.l; localStorage.setItem('se.lang', state.lang);
    document.querySelectorAll('#lang button').forEach((x) => x.classList.toggle('on', x === b));
    loadIncidents(); refreshStats();
  };
});
const voiceBtn = $('#voice');
voiceBtn.textContent = 'Voice alerts: off';
voiceBtn.onclick = () => {
  state.voice = !state.voice;
  voiceBtn.setAttribute('aria-pressed', state.voice);
  voiceBtn.textContent = 'Voice alerts: ' + (state.voice ? 'on' : 'off');
};
function speak(type) {
  if (!state.voice || !('speechSynthesis' in window)) return;
  const u = new SpeechSynthesisUtterance(t(type).say);
  u.lang = { en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN' }[state.lang];
  speechSynthesis.speak(u);
}

// ---------- cameras ----------
async function loadCams() {
  state.cams = await (await fetch('/api/cameras')).json();
  const box = $('#thumbs');
  box.innerHTML = '';
  for (const c of state.cams) {
    const b = document.createElement('button');
    b.className = 'thumb' + (c.id === state.cam ? ' on' : '');
    b.dataset.cam = c.id;
    b.innerHTML = `<img alt="${c.name}"><div class="tag"><span>${c.name}</span><span class="pct">–</span></div>`;
    b.onclick = () => { state.cam = c.id; document.querySelectorAll('.thumb').forEach((x) => x.classList.toggle('on', x === b)); refreshFrames(); };
    box.appendChild(b);
  }
}
function refreshFrames() {
  const now = Date.now();
  const main = state.cams.find((c) => c.id === state.cam);
  if (main) $('#mainName').textContent = main.name;
  $('#mainImg').src = `/api/frame/${state.cam}?t=${now}`;
  document.querySelectorAll('.thumb').forEach((b) => (b.querySelector('img').src = `/api/frame/${b.dataset.cam}?t=${now}`));
}
setInterval(refreshFrames, 1000);

// ---------- live websocket ----------
function connect() {
  const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    for (const [id, c] of Object.entries(d.cams)) {
      const th = document.querySelector(`.thumb[data-cam="${id}"] .pct`);
      if (th) { th.textContent = c.compliance + '%'; th.style.color = c.compliance >= 80 ? '#3DDC84' : c.compliance >= 50 ? '#FFC21A' : '#FF4D4F'; }
      if (id === state.cam) $('#mainStat').textContent = `${c.count} worker${c.count === 1 ? "" : "s"} · ${c.compliance}% compliant · ${c.violations.length} active violations`;
    }
    let workers = 0, okw = 0;
    for (const c of Object.values(d.cams)) { workers += c.count; okw += Math.round((c.compliance / 100) * c.count); }
    setKpi(workers ? Math.round((okw / workers) * 100) : 100, workers);
    for (const e of d.events) { addAlert(e, true); speak(e.type); }
    if (d.events.length) refreshStats();
  };
  ws.onclose = () => setTimeout(connect, 1500);
}
function setKpi(comp, workers) {
  $('#kComp').textContent = comp + '%';
  $('#kWorkers').textContent = workers;
  const fg = $('#ringfg');
  fg.style.strokeDasharray = `${comp} 100`;
  fg.style.stroke = comp >= 80 ? '#3DDC84' : comp >= 50 ? '#FFC21A' : '#FF4D4F';
}

// ---------- alerts ----------
function addAlert(e, fresh) {
  const li = document.createElement('li');
  li.className = `alert ${e.severity}${e.acked ? ' acked' : ''}`;
  li.innerHTML = `<img src="/snapshots/${e.snapshot}" alt=""><div><b>${t(e.type).title}</b><small>${e.camName} · Worker ${e.worker} · ${timeStr(e.ts)}</small></div><button>${e.acked ? 'Done' : 'Ack'}</button>`;
  li.querySelector('img').onclick = () => { state.cam = e.cam; refreshFrames(); };
  li.querySelector('button').onclick = async () => { await fetch(`/api/incidents/${e.id}/ack`, { method: 'POST' }); li.classList.add('acked'); li.querySelector('button').textContent = 'Done'; refreshStats(); };
  const list = $('#alerts');
  fresh ? list.prepend(li) : list.appendChild(li);
  while (list.children.length > 40) list.lastChild.remove();
  if (fresh && (e.severity === 'critical' || e.type === 'zone')) {
    const bn = $('#banner'); bn.hidden = false; bn.textContent = `⚠ ${t(e.type).title} — ${e.camName}`;
    clearTimeout(bn._t); bn._t = setTimeout(() => (bn.hidden = true), 6000);
  }
}
async function loadIncidents() {
  const rows = await (await fetch('/api/incidents?limit=30')).json();
  $('#alerts').innerHTML = '';
  rows.forEach((r) => addAlert(r, false));
}

// ---------- charts & stats ----------
Chart.defaults.color = '#9AA5B1';
Chart.defaults.borderColor = '#262D36';
Chart.defaults.font.family = 'Segoe UI, Inter, system-ui, sans-serif';
function makeCharts() {
  const opts = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, animation: { duration: 500 } };
  state.charts.type = new Chart($('#cType'), { type: 'bar', data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderRadius: 6 }] }, options: { ...opts, indexAxis: 'y', scales: { x: { beginAtZero: true, ticks: { precision: 0 } } } } });
  state.charts.trend = new Chart($('#cTrend'), { type: 'line', data: { labels: [], datasets: [{ data: [], borderColor: '#3DDC84', backgroundColor: 'rgba(61,220,132,.12)', fill: true, tension: 0.35, pointRadius: 0 }] }, options: { ...opts, scales: { y: { min: 0, max: 100, ticks: { callback: (v) => v + '%' } } } } });
  state.charts.cam = new Chart($('#cCam'), { type: 'bar', data: { labels: [], datasets: [{ data: [], backgroundColor: '#FFC21A', borderRadius: 6 }] }, options: { ...opts, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } } });
}
async function refreshStats() {
  const s = await (await fetch('/api/stats')).json();
  $('#kOpen').textContent = s.open;
  $('#kTotal').textContent = s.total;
  $('#feedCount').textContent = `${s.total} today`;
  const types = Object.keys(s.byType);
  const ct = state.charts.type;
  ct.data.labels = types.map((k) => t(k).title);
  ct.data.datasets[0].data = types.map((k) => s.byType[k]);
  ct.data.datasets[0].backgroundColor = types.map((k) => TYPE_COLORS[k] || '#888');
  ct.update();
  const tr = state.charts.trend;
  tr.data.labels = s.trend.map((p) => new Date(p.t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
  tr.data.datasets[0].data = s.trend.map((p) => p.v);
  tr.update();
  const cc = state.charts.cam;
  cc.data.labels = Object.keys(s.byCam);
  cc.data.datasets[0].data = Object.values(s.byCam);
  cc.update();
}
setInterval(refreshStats, 5000);

$('#genReport').onclick = async () => {
  $('#reportText').textContent = 'Analysing shift data…';
  const r = await (await fetch('/api/report')).json();
  $('#reportText').textContent = r.text;
};

// ---------- ad-hoc image / webcam ----------
async function analyzeBlob(blob, cam) {
  const fd = new FormData(); fd.append('file', blob, 'frame.jpg');
  const r = await (await fetch(`/api/analyze?cam=${cam}`, { method: 'POST', body: fd })).json();
  $('#toolImg').hidden = false; $('#toolImg').src = r.image;
  const v = r.result.violations;
  $('#toolMsg').textContent = `${r.result.count} worker(s) · ${r.result.compliance}% compliant` + (v.length ? ' · ' + [...new Set(v.map((x) => t(x.type).title))].join(', ') : ' · all clear');
}
$('#upload').onchange = (e) => e.target.files[0] && analyzeBlob(e.target.files[0], 'upload');
$('#webcam').onclick = async () => {
  const video = $('#cam');
  if (video.srcObject) { video.srcObject.getTracks().forEach((t) => t.stop()); video.srcObject = null; video.hidden = true; $('#webcam').textContent = 'Start webcam'; return; }
  try {
    video.srcObject = await navigator.mediaDevices.getUserMedia({ video: true });
    $('#webcam').textContent = 'Stop webcam';
    const c = document.createElement('canvas');
    const loop = async () => {
      if (!video.srcObject) return;
      c.width = video.videoWidth; c.height = video.videoHeight;
      c.getContext('2d').drawImage(video, 0, 0);
      c.toBlob(async (b) => { try { await analyzeBlob(b, 'webcam'); } catch {} setTimeout(loop, 800); }, 'image/jpeg', 0.8);
    };
    video.onloadeddata = loop;
  } catch { $('#toolMsg').textContent = 'Camera permission denied.'; }
};

(async function init() {
  state.msgs = await (await fetch('/api/messages')).json();
  makeCharts();
  await loadCams();
  refreshFrames();
  await loadIncidents();
  await refreshStats();
  connect();
})();
