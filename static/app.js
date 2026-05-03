'use strict';

const $ = id => document.getElementById(id);

const DAYS   = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

// Last-fetched data; re-used to refresh minute counts between API calls
let cachedStops = null;

// ── Clock ─────────────────────────────────────────────────────────────────────

function updateClock() {
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  $('clock').textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  $('date-display').textContent =
    `${DAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]} ${now.getFullYear()}`;
}

setInterval(updateClock, 1000);
updateClock();

// ── Transit rendering ─────────────────────────────────────────────────────────

function minuteLabel(realtimeMs) {
  const diff = Math.round((realtimeMs - Date.now()) / 60_000);
  if (diff <= 0) return { text: 'now',          cls: 'now'  };
  if (diff <= 3) return { text: `${diff} min`,  cls: 'soon' };
  return               { text: `${diff} min`,  cls: ''     };
}

function renderStop(stop) {
  if (stop.error) {
    return `<div class="stop-card">
      <div class="stop-header">${stop.stop}</div>
      <div class="error-msg">⚠ ${stop.error}</div>
    </div>`;
  }

  if (!stop.departures.length) {
    return `<div class="stop-card">
      <div class="stop-header">${stop.stop}</div>
      <div class="placeholder">No departures found</div>
    </div>`;
  }

  const rows = stop.departures.map(d => {
    const lbl   = minuteLabel(d.realtime_ms);
    const delay = d.delay > 0
      ? `<span class="delay-badge">+${d.delay}'</span>` : '';
    return `<div class="departure-row">
      <span class="line-badge" style="background:${d.color}">${d.line}</span>
      <span class="destination">${d.destination}</span>
      <div class="time-col">
        <span class="minutes ${lbl.cls}">${lbl.text}</span>
        ${delay}
      </div>
    </div>`;
  }).join('');

  return `<div class="stop-card">
    <div class="stop-header">${stop.stop}</div>
    ${rows}
  </div>`;
}

function renderTransit(stops) {
  $('stops-container').innerHTML = stops.map(renderStop).join('');
}

// ── Weather rendering ─────────────────────────────────────────────────────────

function renderWeather(w) {
  if (w.error) {
    $('weather-current').innerHTML  = `<div class="error-msg">⚠ ${w.error}</div>`;
    $('weather-forecast').innerHTML = '';
    return;
  }

  const c = w.current;
  $('weather-current').innerHTML = `
    <div class="weather-location">${w.location}</div>
    <div class="weather-main">
      <span class="weather-icon">${c.icon}</span>
      <span class="weather-temp">${c.temp}°</span>
    </div>
    <div class="weather-desc">${c.description}</div>
    <div class="weather-meta">
      <span>Feels like ${c.feels_like}°</span>
      <span>${c.humidity}% humidity</span>
      <span>💨 ${c.wind_speed} km/h</span>
    </div>`;

  $('weather-forecast').innerHTML = w.forecast.map(f => `
    <div class="forecast-row">
      <span class="forecast-time">${f.time}</span>
      <span class="forecast-icon">${f.icon}</span>
      <span class="forecast-temp">${f.temp}°</span>
      <div class="precip-wrap">
        <div class="precip-bar">
          <div class="precip-fill" style="width:${f.precip_prob}%"></div>
        </div>
        <span class="precip-pct">${f.precip_prob}%</span>
      </div>
    </div>`).join('');
}

// ── Data fetching ─────────────────────────────────────────────────────────────

async function fetchData() {
  try {
    const r = await fetch('/api/data');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();

    cachedStops = data.stops;
    renderTransit(data.stops);
    renderWeather(data.weather);

    const t = new Date(data.updated_at);
    const pad = n => String(n).padStart(2, '0');
    $('status').textContent = `Updated ${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`;
    $('status').className = '';
  } catch (err) {
    console.error('Fetch error:', err);
    $('status').textContent = `⚠ ${err.message}`;
    $('status').className = 'error';
  }
}

// Re-render minute counts from cached data between API fetches
setInterval(() => {
  if (cachedStops) renderTransit(cachedStops);
}, 15_000);

fetchData();
setInterval(fetchData, REFRESH_INTERVAL);
