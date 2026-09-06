function step(){
  const beat = frame < B2 ? 0 : frame < B3 ? 1 : frame < B4 ? 2 : 3;
  // long-exposure decay
  ctx.fillStyle = hexToRgba(CREAM, 0.988);   // cream-derived long-exposure decay
  ctx.fillRect(0, 0, W, H);
  drawChrome();

  // spawn — routes activate staggered; cadence settles 10-14s so the verdict owns the frame
  for (const flow of flows){
    if (frame < flow.startFrame) continue;
    const ramp = Math.min(1, (frame - flow.startFrame) / 25);
    const fi = flows.indexOf(flow);
    const settle = frame >= 300 ? 1 + 0.25 * eInCubic(clamp01((frame - 300) / 120)) : 1;
    for (let ci = 0; ci < flow.paths.length; ci++){
      const pth = flow.paths[ci];
      if (pth.w <= 0.001) continue;
      const routeStart = flow.startFrame + pth._rs;
      if (frame < routeStart) continue;
      const dIn = eOutCubic(clamp01((frame - routeStart) / 21));  // ~700ms draw-in
      let weff = pth.w2;                                   // matrix from frame one
      if (RECAP || NET) weff = Math.max(0.05, weff);
      else weff = Math.max(0.15, weff);
      const every = Math.max(5, Math.round(spawnEvery(Math.max(0.02, weff)) * settle));
      if ((frame % every) === ((ci + fi) % every) && rng() < ramp){
        // hierarchy visible while drawing (two channels: width from w2, opacity from mS);
        // the subtraction beat then DRAINS cancelled routes on both channels (staged)
        const sv = Math.max(0, pth.s2);
        const sF = 0.90 + 0.10 * sv;
        const msr = Math.max(0, pth.mS || 0) / GMAX;
        let str = sF * (0.18 + 0.82 * Math.pow(Math.min(1, msr), 0.7)) * SOFT * dIn;
        let pw = weff;
        if (RECAP || NET){ str *= (0.78 + 0.44 * rng()); pw *= (0.85 + 0.30 * rng()); }
        particles.push({flow: fi, ci, born: frame, t: 0.002, spd: 0, hist: [], w: Math.max(0.05, pw), str,
                        off: 1.8 + 4.2 * rng(), ph: rng() * 6.2832, fr: 2.0 + 1.8 * rng(), die: null});
      }
    }
  }
  // move + draw
  for (let i = particles.length - 1; i >= 0; i--){
    const p = particles[i];
    const flow = flows[p.flow], pth = flow.paths[p.ci];
    if (!p.spd) p.spd = (1 / PFRAMES) * (0.9 + 0.2 * rng());
    const ageF = clamp01((frame - p.born) / 12);          // spawn at rest, ramp to cruise
    p.t += p.spd * eOutQuad(ageF);
    const arrived = p.t >= 1;
    const raw = pointAt(pth, arrived ? 1 : p.t);
    // lateral weave — organic brush ribbon instead of a plotted line
    const tan = tangentAt(pth, Math.min(0.999, p.t));
    const wob = Math.sin(p.ph + p.t * p.fr * 6.2832);
    const pos = [raw[0] - tan[1] * p.off * wob, raw[1] + tan[0] * p.off * wob];
    p.hist.push(pos);
    if (p.hist.length > TRAIL) p.hist.shift();
    if (p.hist.length > 1){
      if (arrived && p.die == null) p.die = 5;
      const dF = p.die != null ? Math.max(0, p.die / 5) : 1;
      const k = 1 + (pth._kEnd - 1) * drainE(pth, frame);  // staged subtraction per route
      drawStreak(flow.col, p.hist, p.w, p.str * dF, k);
      // particle head: brighter leading tip so flow direction is legible
      if (p.die == null && flow.col !== '#FFFFFF' && flow.col !== 'white'){
        const H = p.hist;
        const hlw = Math.max(1.0, Math.min(3.4, 1.1 + 2.8 * Math.pow(p.w, 0.9)));
        ctx.strokeStyle = lighten(flow.col, 0.45);
        ctx.globalAlpha = Math.min(1, 0.5 * p.str * (0.5 + 0.5 * k));
        ctx.lineWidth = Math.max(1.0, hlw * 1.15);
        ctx.beginPath();
        const n0 = Math.max(0, H.length - 4);
        for (let h = n0; h < H.length; h++){ const q = H[h]; h === n0 ? ctx.moveTo(q[0], q[1]) : ctx.lineTo(q[0], q[1]); }
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
      if (p.die != null && --p.die <= 0){ particles.splice(i, 1); continue; }
    }
  }
  // trim runaway particles
  while (particles.length > 900) particles.shift();

  // caption / verdict -------------------------------------------------------
  // one narrative slot: phases during the draw (crossfaded, next line leads by ~300ms),
  // verdict reveal choreographed at the end (ease-out-expo + tracking settle)
  const capY = 138;
  const verdictAt = B4;
  if (frame < verdictAt){
    const caps = [
      poss(TN) + (RECAP || NET ? ' real chains draw up' : ' scoring chains draw up'),
      poss(BN) + (RECAP || NET ? ' real chains draw down' : ' scoring chains draw down'),
      NET ? 'the net lands \u2014 routes the other end cancels drain to a drip'
          : 'the model\u2019s net \u2014 cancelled routes drain to a drip'
    ];
    const bs = [0, B2, B3][beat], ns = [B2, B3, verdictAt][beat];
    const aIn = clamp01((frame - Math.max(0, bs - 9)) / 12);
    const aOut = clamp01(((ns - 9) - frame) / 10);
    const capA = Math.min(aIn, aOut);
    if (capA > 0.01){
      ctx.globalAlpha = capA;
      typeLine(caps[beat], cx, capY - (1 - capA) * 8, 12, TAUPE);   // 8px rise on entry
      ctx.globalAlpha = 1;
    }
  } else if (V.winner || R.home_name){
    const wName = (V.winner || (R.home_score >= R.away_score ? R.home_name : R.away_name) || '').toUpperCase();
    const wMar = NET ? Math.abs((R.home_score||0) - (R.away_score||0)) : Math.round(V.margin || 0);
    const e1 = eOutQuint(clamp01((frame - verdictAt) / 30));          // name grows into place ~1s
    ctx.globalAlpha = e1;
    ctx.save();
    ctx.translate(cx, 130); ctx.scale(0.88 + 0.12 * e1, 0.88 + 0.12 * e1);
    typeLine(wName, 0, 0, 28, NAVYINK, 'bold', 0, DISPLAY);
    ctx.restore();
    ctx.globalAlpha = 1;
    const e2 = eOutExpo(clamp01((frame - (verdictAt + 21)) / 12));     // BY line after the name settles
    if (e2 > 0.01){
      ctx.globalAlpha = e2;
      typeLine('BY ' + wMar, cx, 158, 15, NAVYINK, 'bold', Math.round(7 - 6 * e2));  // tracking settles
      ctx.globalAlpha = 1;
    }
    // grade (Austin's ruling 2026-09-05): the model's own grade F..A+ always
    // sits under the BY line on model-call cards (pred + recap; net's margin
    // is the actual result — no call to grade)
    const GRADE = (NET || !V.grade) ? null : V.grade;
    if (GRADE){
      const eg = eOutExpo(clamp01((frame - (verdictAt + 27)) / 12));
      if (eg > 0.01){
        ctx.globalAlpha = 0.85 * eg;
        typeLine('GRADE ' + GRADE, cx, 170, 9.5, MUTED, 'normal', 1.5, SANS);
        ctx.globalAlpha = 1;
      }
    }
    // detail line (last, quiet): pred = the projected scoreline; recap = the
    // ACTUAL result next to the model call (won-by is computed from result,
    // which carries the real scores; ruling 2026-09-05)
    const detailY = 184;
    const Vp = V.projected || [];
    if (Vp.length === 2){
      const e3 = eOutExpo(clamp01((frame - (verdictAt + 33)) / 12));
      if (e3 > 0.01){
        ctx.globalAlpha = 0.9 * e3;
        typeLine('projected ' + Vp[0] + ' \u2013 ' + Vp[1], cx, detailY, 11.5, TAUPE);
        ctx.globalAlpha = 1;
      }
    } else if (RECAP && R.home_score != null && R.away_score != null){
      const e3 = eOutExpo(clamp01((frame - (verdictAt + 33)) / 12));
      if (e3 > 0.01){
        const actM = Math.abs(R.home_score - R.away_score);
        const actW = (R.home_score >= R.away_score ? R.home_name : R.away_name).toUpperCase();
        ctx.globalAlpha = 0.9 * e3;
        typeLine((actW === wName ? 'won by ' : 'ACTUAL: ' + actW + ' by ') + actM,
                 cx, detailY, 11.5, TAUPE);
        ctx.globalAlpha = 1;
      }
    }
  }

  // inner end labels — solid cream plates hugging the goal RINGS (video
  // layout: label BELOW top ring, ABOVE bottom ring). They mask ONLY the
  // converged mouth of the goal (~10px of final approach); the old ±61px
  // offset sat in wide-web territory and, with the shared web, covered the
  // mirrored team's defensive-origin band (chains STARTED under the plate).
  function plate2(gy, txt){
    const y0 = gy > cy ? gy - 36 : gy + 10;
    ctx.beginPath();
    ctx.roundRect(cx - 135, y0, 270, 26, 13);
    ctx.fillStyle = CREAM; ctx.fill();
    typeLine(txt, cx, y0 + 13, 11, '#565047');
  }
  plate2(topY, 'WHERE ' + TN.toUpperCase() + ' SCORES');
  plate2(botY, 'WHERE ' + BN.toUpperCase() + ' SCORES');
  drawAnchors();

  // legend — colour chips + team names (worn colours from the exporter)
  const legY = 1126;
  const p1 = TN.toUpperCase() + '\u2019s chains', p2 = BN.toUpperCase() + '\u2019s chains';
  const p3 = '\u00b7  flow = ' + (NET ? 'the actual net' : 'the model\u2019s net');
  ctx.font = '400 10.5px ' + SERIF;
  const w1 = ctx.measureText(p1).width, w2 = ctx.measureText(p2).width, w3 = ctx.measureText(p3).width;
  const gap = 14, chip = 8, cg = 7;
  const total = chip + cg + w1 + gap + chip + cg + w2 + gap + w3;
  let x = cx - total / 2;
  function chipAt(xc, col){
    ctx.beginPath(); ctx.roundRect(xc, legY - chip / 2, chip, chip, 2); ctx.fillStyle = col; ctx.fill();
    if (col === '#FFFFFF' || col === 'white'){ ctx.lineWidth = 1; ctx.strokeStyle = '#57534A'; ctx.stroke(); }
  }
  chipAt(x, TCOL.top); x += chip + cg;
  typeLine(p1, x + w1 / 2, legY, 10.5, FAINT); x += w1 + gap;
  chipAt(x, TCOL.bottom); x += chip + cg;
  typeLine(p2, x + w2 / 2, legY, 10.5, FAINT); x += w2 + gap;
  typeLine(p3, x + w3 / 2, legY, 10.5, FAINT);
  typeLine(RECAP ? 'the subtraction lands \u2014 routes it cancels drain to a drip'
                 : (NET ? 'every real route weighed against the other end \u2014 the game draws its own verdict'
                        : 'thickness + opacity = surviving weight \u00b7 faded = cancelled'),
           cx, 1150, 9.5, FAINT);

  frame++;
}
window.__advance = step;
step();
