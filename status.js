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
function prettyStatus(s){ return s==='operational'?'Operational':s==='degraded_performance'?'Degraded performance':s==='major_outage'?'Major outage':'Unknown'; }
function dotClass(s){ return s==='operational'?'ok':s==='degraded_performance'?'minor':s==='major_outage'?'major':''; }
function uptimeClass(p){ if (p>=0.999) return 'ok'; if (p>=0.99) return 'minor'; return 'major'; }
function chunk(arr, size){ const out=[]; for(let i=0;i<arr.length;i+=size) out.push(arr.slice(i,i+size)); return out; }

load().catch(err => {
  console.error(err);
  const el = document.getElementById('overall');
  el.className = 'badge down';
  el.textContent = 'Failed to load health.json';
});