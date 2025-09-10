// status.js
async function load() {
  const res = await fetch('health.json?ts=' + Date.now(), { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch health.json: ' + res.status);
  const data = await res.json();

  // updatedAt
  const updatedAt = new Date(data.updatedAt || Date.now());
  document.getElementById('updatedAt').textContent = updatedAt.toLocaleString();

  // overall banner (use the "Global" component if present, else first)
  const overall = (data.components || []).find(c => /global/i.test(c.name)) || (data.components || [])[0] || { status: 'operational' };
  const overallMap = {
    operational: { cls: 'ok', txt: 'All systems operational' },
    degraded_performance: { cls: 'degraded', txt: 'Partial degradation' },
    major_outage: { cls: 'down', txt: 'Major outage' },
  };
  const ov = overallMap[overall.status] || overallMap.operational;
  const banner = document.getElementById('overall');
  banner.className = 'badge ' + ov.cls;
  banner.textContent = ov.txt;

  // summary line
  const summary = document.getElementById('summary');
  summary.textContent = (data.components || [])
    .filter(c => !/global/i.test(c.name))
    .map(c => `${c.name}: ${prettyStatus(c.status)}`)
    .join(' · ');

  // components list
  const ul = document.getElementById('components');
  ul.innerHTML = '';
  (data.components || []).filter(c => !/global/i.test(c.name)).forEach(c => {
    const li = document.createElement('li');
    const left = document.createElement('div'); left.className = 'name'; left.textContent = c.name;
    const right = document.createElement('div'); right.className = 'state';
    const dot = document.createElement('span'); dot.className = 'dot ' + dotClass(c.status);
    const text = document.createElement('span'); text.textContent = prettyStatus(c.status);
    right.append(dot, text); li.append(left, right); ul.append(li);
  });

  // incidents
  const incDiv = document.getElementById('incidents');
  const incs = data.incidents || [];
  if (incs.length === 0) {
    incDiv.textContent = 'No incidents reported.';
  } else {
    incDiv.innerHTML = '';
    incs.slice(0, 5).forEach(inc => {
      const d = document.createElement('div'); d.className = 'incident';
      const title = document.createElement('div'); title.className = 'title'; title.textContent = inc.title || 'Incident';
      const time = document.createElement('div'); time.className = 'time';
      const start = inc.startTime ? new Date(inc.startTime).toLocaleString() : '';
      const end = inc.endTime ? new Date(inc.endTime).toLocaleString() : '';
      time.textContent = start + (end ? (' — ' + end) : '');
      const desc = document.createElement('div'); desc.textContent = inc.description || '';
      d.append(title, time, desc); incDiv.append(d);
    });
  }

  // uptime (expects array of {date:'YYYY-MM-DD', pct:0..1})
  const upDiv = document.getElementById('uptime');
  upDiv.innerHTML = '';
  const days = (data.uptime || []).slice(-91);
  const weeks = chunk(days, 7);
  weeks.forEach(week => {
    const col = document.createElement('div'); col.className = 'week';
    week.forEach(day => {
      const c = document.createElement('div'); c.className = 'cell ' + uptimeClass(day.pct ?? 1);
      const pct = (day.pct ?? 1) * 100;
      c.title = `${day.date || ''}: ${pct.toFixed(3)}%`;
      col.append(c);
    });
    upDiv.append(col);
  });
}


fetch('health.json')
  .then(r => r.json())
  .then(h => {
    const root = document.getElementById('uptime');
    // Top row: overall (h.uptime)
    buildUptimeRow(root, 'APIs', h.uptime, (date) => findIncidentsFor(h.incidents, date));

    // Expand per-component rows if user opens the group
    // Example: render a few
    const comps = Object.keys(h.daily_uptime || {}).sort();
    for (const name of comps) {
      buildUptimeRow(root, `• ${name}`, h.daily_uptime[name], (date) => findIncidentsFor(h.incidents, date, name));
    }
  });

function findIncidentsFor(incidents, date, nameFilter) {
  if (!incidents) return [];
  // naïve: match incidents whose startTime falls on that date (adjust if you want full span overlap)
  return incidents.filter(inc => {
    if (nameFilter && !(inc.title || '').includes(nameFilter)) return false;
    const d = (inc.startTime || '').slice(0,10);
    return d === date;
  });
}

function prettyStatus(s){ return s==='operational'?'Operational':s==='degraded_performance'?'Degraded performance':s==='major_outage'?'Major outage':'Unknown'; }
function dotClass(s){ return s==='operational'?'ok':s==='degraded_performance'?'minor':s==='major_outage'?'major':''; }
function uptimeClass(p){ if (p>=0.999) return 'ok'; if (p>=0.99) return 'minor'; return 'major'; }
function chunk(arr, size){ const out=[]; for(let i=0;i<arr.length;i+=size) out.push(arr.slice(i,i+size)); return out; }

function colorFor(pct) {
  if (pct == null) return 'u-na';       // gray for missing
  if (pct >= 0.999) return 'u-good';    // green
  if (pct >= 0.995) return 'u-ok';      // yellow
  if (pct >= 0.970) return 'u-warn';    // orange
  return 'u-bad';                        // red
}

function lastNDays(n) {
  const days = [];
  const today = new Date(); today.setUTCHours(0,0,0,0);
  for (let i = n-1; i >= 0; i--) {
    const d = new Date(today); d.setUTCDate(today.getUTCDate() - i);
    days.push(d.toISOString().slice(0,10)); // YYYY-MM-DD
  }
  return days;
}

function mapSeriesByDate(series) {
  const map = {};
  (series || []).forEach(r => { map[r.date] = r.pct; });
  return map;
}

function buildUptimeRow(container, label, dailySeries, incidentsForDay = (/*date*/)=>[]) {
  const row = document.createElement('div');
  row.className = 'u-row';

  const title = document.createElement('div');
  title.className = 'u-title';
  title.textContent = label;
  row.appendChild(title);

  const bar = document.createElement('div');
  bar.className = 'u-bar';
  const byDate = mapSeriesByDate(dailySeries);
  for (const d of lastNDays(90)) {
    const pct = byDate[d];   // 0..1 or undefined
    const dot = document.createElement('div');
    dot.className = `u-day ${colorFor(pct)}`;
    dot.setAttribute('title', `${d} — ${pct != null ? (pct*100).toFixed(2)+'% uptime' : 'No data'}`);
    // Optional: show incidents count in tooltip
    const inc = incidentsForDay(d);
    if (inc.length) dot.setAttribute('title', `${d} — ${(pct*100).toFixed(2)}% uptime\n${inc.length} incident(s)`);
    bar.appendChild(dot);
  }
  row.appendChild(bar);
  container.appendChild(row);
}

load().catch(err => {
  console.error(err);
  const el = document.getElementById('overall');
  el.className = 'badge down';
  el.textContent = 'Failed to load health.json';
});