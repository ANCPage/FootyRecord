function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;}}
const rng = mulberry32(THEME.seed);


function poss(n){ return n.charAt(n.length-1).toLowerCase() === 's' ? n + '\u2019' : n + '\u2019s'; }
function typeLine(txt, x, y, size, col, weight, ls, face){
  ctx.font = (weight === 'bold' ? '700 ' : (weight === 'light' ? '300 ' : '400 ')) + size + 'px ' + (face || SERIF);
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.letterSpacing = (ls || 0) + 'px';
  ctx.lineJoin = 'round'; ctx.lineWidth = Math.max(2.5, size * 0.30);
  ctx.strokeStyle = CREAM; ctx.strokeText(txt, x, y);
  ctx.fillStyle = col; ctx.fillText(txt, x, y);
  ctx.letterSpacing = '0px';
}
// ---- motion helpers (animator pass 2026-09-05) ----
function clamp01(v){ return v < 0 ? 0 : v > 1 ? 1 : v; }
const eOutQuad  = t => 1 - (1 - t) * (1 - t);
const eOutCubic = t => 1 - Math.pow(1 - t, 3);
const eOutQuint = t => 1 - Math.pow(1 - t, 5);
const eInCubic  = t => t * t * t;
const eOutExpo  = t => t >= 1 ? 1 : 1 - Math.pow(2, -10 * t);
function lighten(hex, f){
  if (hex === '#FFFFFF' || hex === 'white') return hex;
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  const m = c => Math.round(c + (255 - c) * f);
  return 'rgb(' + m(r) + ',' + m(g) + ',' + m(b) + ')';
}
function hexToRgba(hex, a){
  const n = parseInt(hex.slice(1), 16);
  return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
}

// smooth a chain polyline through its own nodes (Catmull-Rom, uniform)
function smoothPath(pts){
  if (pts.length < 3) return pts;
  const out = [], P = pts;
  for (let i = 0; i < P.length - 1; i++){
    const p0 = P[Math.max(0, i - 1)], p1 = P[i], p2 = P[i + 1], p3 = P[Math.min(P.length - 1, i + 2)];
    for (let s = 0; s < 10; s++){
      const t = s / 10;
      const t2 = t * t, t3 = t2 * t;
      out.push([
        0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
        0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
      ]);
    }
  }
  out.push(P[P.length - 1]);
  return out;
}

const flows = [];
for (const end of ['top', 'bottom']){ const col = TCOL[end];
  const arr = (DATA.ends[end] || {}).own || [];
  if (!arr.length) continue;
  let maxMS = 0.0001;
  for (const c of arr) maxMS = Math.max(maxMS, c.mS || 0);
  flows.push({end, col, paths: arr, startFrame: (end === 'top' ? B1 : B2) + 9, maxMS});
}

// ---- chrome ---------------------------------------------------------------
function drawChrome(){
  ctx.fillStyle = CREAM; ctx.fillRect(0, 0, W, H);
  // editorial serif masthead stack — matches the reference grammar
  typeLine('FINGERPRINT', cx, 33, 19, NAVYINK, 'bold', 2, DISPLAY);
  typeLine((DATA.round_label || '').toUpperCase(), cx, 68, 10.5, MUTED, 'normal', 1, SANS);
  typeLine(TN.toUpperCase() + ' v ' + BN.toUpperCase(), cx, 106, 16, NAVYINK, 'bold');
  // oval field — the eye meets the field before the first head (0.7s ease-out)
  const fa = eOutQuad(clamp01(frame / 21));
  ctx.globalAlpha = fa;
  ctx.beginPath(); ctx.ellipse(cx, cy, rx, ry, 0, 0, 6.2832);
  ctx.fillStyle = '#F1EDE3'; ctx.fill();
  ctx.lineWidth = 1.5; ctx.strokeStyle = '#DDD6C4'; ctx.stroke();
  for (const f of [0.32, 0.55, 0.78]){
    ctx.beginPath(); ctx.ellipse(cx, cy, rx*f, ry*f, 0, 0, 6.2832);
    ctx.lineWidth = 0.8; ctx.strokeStyle = '#E0DAC8'; ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

// crisp anchor nodes — target icon: dark centre dot in a team-coloured ring
function drawAnchors(){
  for (const [gy, col] of [[topY, TCOL.top], [botY, TCOL.bottom]]){
    ctx.beginPath(); ctx.arc(cx, gy, 11, 0, 6.2832);
    ctx.lineWidth = 2.4; ctx.strokeStyle = col; ctx.stroke();
    if (col === '#FFFFFF' || col === 'white'){
      ctx.beginPath(); ctx.arc(cx, gy, 11, 0, 6.2832);
      ctx.lineWidth = 1; ctx.strokeStyle = '#57534A'; ctx.stroke();
    }
    ctx.beginPath(); ctx.arc(cx, gy, 8.5, 0, 6.2832);
    ctx.fillStyle = CREAM; ctx.fill();
    ctx.beginPath(); ctx.arc(cx, gy, 5.5, 0, 6.2832);
    ctx.fillStyle = '#14181F'; ctx.fill();
  }
}

// ---- particle drawing -----------------------------------------------------
function drawStreak(col, hist, w, str, k){
  // k = concession drain (1 before the subtraction, ->0.45+0.55*s2 after):
  // BOTH channels reduce together — width thins AND opacity fades on cancelled routes.
  if (hist.length < 2 || str <= 0.01) return;
  let lw = Math.max(0.7, (Math.max(1.0, Math.min(3.4, 1.1 + 2.8 * Math.pow(w, 0.9)))) * k);
  const aK = 0.5 + 0.5 * k;
  const WHITE_RIBBON = col === '#FFFFFF' || col === 'white';
  ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  if (!WHITE_RIBBON){
    ctx.strokeStyle = col;
    // halo
    ctx.globalAlpha = Math.min(1, 0.085 * str * aK);
    ctx.lineWidth = lw * 2.6;
    ctx.beginPath();
    for (let i = 0; i < hist.length; i++){ const p = hist[i]; i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); }
    ctx.stroke();
    // core
    ctx.globalAlpha = Math.min(1, 0.38 * str * aK);
    ctx.lineWidth = lw;
    ctx.beginPath();
    for (let i = 0; i < hist.length; i++){ const p = hist[i]; i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); }
    ctx.stroke();
  } else {
    // white clash guernsey: ink under-stroke + white core reads on cream
    ctx.strokeStyle = '#3A3732';
    ctx.globalAlpha = Math.min(1, 0.30 * str * aK);
    ctx.lineWidth = lw * 2.2;
    ctx.beginPath();
    for (let i = 0; i < hist.length; i++){ const p = hist[i]; i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); }
    ctx.stroke();
    ctx.strokeStyle = '#FFFFFF';
    ctx.globalAlpha = Math.min(1, 0.85 * str * aK);
    ctx.lineWidth = Math.max(0.8, lw - 0.4);
    ctx.beginPath();
    for (let i = 0; i < hist.length; i++){ const p = hist[i]; i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); }
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

const particles = [];
function spawnEvery(weff){
  return Math.max(5, Math.min(34, Math.round(20 - 18 * Math.pow(weff, 0.45))));
}
function pointAt(pth, t){
  const L = pth._L, pts = pth.pts;
  const d = t * L[L.length - 1];
  let lo = 0, hi = L.length - 1;
  while (hi - lo > 1){ const m = (lo + hi) >> 1; L[m] <= d ? lo = m : hi = m; }
  const f = (d - L[lo]) / Math.max(1e-6, L[hi] - L[lo]);
  return [pts[lo][0] + (pts[hi][0] - pts[lo][0]) * f, pts[lo][1] + (pts[hi][1] - pts[lo][1]) * f];
}
// unit tangent at t (for lateral weave offsets)
function tangentAt(pth, t){
  const L = pth._L, pts = pth.pts;
  const d = Math.min(L[L.length - 1] - 1e-6, Math.max(1e-6, t * L[L.length - 1]));
  let lo = 0, hi = L.length - 1;
  while (hi - lo > 1){ const m = (lo + hi) >> 1; L[m] <= d ? lo = m : hi = m; }
  const dx = pts[hi][0] - pts[lo][0], dy = pts[hi][1] - pts[lo][1];
  const len = Math.hypot(dx, dy) || 1;
  return [dx / len, dy / len];
}
for (const f of flows){
  f.paths.forEach(p => {
    p.pts = smoothPath(p.pts);          // liquid curves through the real nodes
    const pts = p.pts; const L = [0];
    for (let i = 1; i < pts.length; i++)
      L.push(L[i-1] + Math.hypot(pts[i][0]-pts[i-1][0], pts[i][1]-pts[i-1][1]));
    p._L = L;
  });
}

let GMAX = 0.0001;                       // global matrix max — the net is between teams
for (const f of flows) for (const c of f.paths) GMAX = Math.max(GMAX, c.mS || 0);

// per-route activation stagger (channels build organically, not all at once)
for (const f of flows){
  const fi = flows.indexOf(f);
  f.paths.forEach((p, ci) => {
    p._rs = Math.min(34, Math.floor(ci * 2.6) + ((ci * 13 + fi * 7) % 3)); // ~90-180ms apart
    const sv = Math.max(0, p.s2 || 0);
    // staged subtraction: survivors hold, middle routes get a fast 'suck',
    // the weakest ghosts ease out slowly, staggered by route hash
    p._kEnd = 0.45 + 0.55 * sv;
    if (sv >= 0.85) p._dr = {kind: 'hold'};
    else if (sv >= 0.40) p._dr = {kind: 'suck', t0: B3, dur: 21};
    else p._dr = {kind: 'ghost', t0: B3 + 21 + ((ci * 7 + fi * 3) % 20), dur: 54};
  });
}
function drainE(pth, fr){
  const d = pth._dr;
  if (d.kind === 'hold') return 1;
  if (fr < d.t0) return 0;
  const t = clamp01((fr - d.t0) / d.dur);
  return d.kind === 'suck' ? eOutCubic(t) : eOutQuint(t);
}

let frame = 0;
