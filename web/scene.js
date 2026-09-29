/* Scene store + canvas renderer for the Endless Ball Machine.
 *
 * Python (ebm.scene_export via ebm.web_demo) owns physics and mirrors scene
 * state here: topology/style as rare events, body poses as one typed-array
 * batch per animation frame. All canvas work happens in JS, so the per-frame
 * cost is a handful of batched draw calls instead of thousands of Pyodide
 * proxy crossings.
 *
 * Wire format (see scene_export.py):
 *   events:  nested arrays, e.g. ["tile_add", owner, ox, oy, statics, dynVisuals, dynBodies]
 *   shapes:  [0, x1, y1, x2, y2, r, fill, stroke]  segment
 *            [1, x, y, r, fill, stroke]            circle
 *            [2, r, fill, stroke, [x1, y1, ...]]   polygon
 *   colors:  [r, g, b, a] integers 0..255
 *   poses:   ids (Uint32Array, idStride lanes per body) + floats (Float64Array
 *            x, y, angle per body), parallel arrays.
 */
(() => {
  const TILE = 400;
  const TAU = Math.PI * 2;
  const PAPER = "#f4e8c8";
  const GRID = "rgba(86,70,43,.035)";
  const DYNAMIC_INTERVAL = 1000 / 30;

  let staticCanvas = null;
  let dynamicCanvas = null;
  let sctx = null;
  let dctx = null;

  const tiles = new Map();      // owner -> {ox, oy, statics, dynVisuals, bodyIds}
  const dynBodies = new Map();  // bodyId -> {shapes}
  const balls = new Map();      // bodyId -> {r, fill, stroke, paused}

  let poseIds = new Uint32Array(0);
  let poseFloats = new Float64Array(0);
  let poseStride = 1;
  let poseCount = 0;

  let vp = { x: 0, y: 0, zoom: 0.5 };
  let staticDirty = true;
  let lastDynamic = 0;
  let lastW = 0;
  let lastH = 0;
  const stats = {
    staticFrames: 0, staticTotalMs: 0, staticMaxMs: 0,
    dynamicFrames: 0, dynamicTotalMs: 0, dynamicMaxMs: 0,
    eventCount: 0,
  };

  function css(color) {
    if (!color || color[3] === 0) return null;
    return `rgba(${color[0]},${color[1]},${color[2]},${(color[3] / 255).toFixed(4)})`;
  }

  function makeShape(e) {
    if (e[0] === 0) return { t: 0, x1: e[1], y1: e[2], x2: e[3], y2: e[4], r: e[5], fill: css(e[6]), stroke: css(e[7]) };
    if (e[0] === 1) return { t: 1, x: e[1], y: e[2], r: e[3], fill: css(e[4]), stroke: css(e[5]) };
    return { t: 2, r: e[1], fill: css(e[2]), stroke: css(e[3]), pts: e[4] };
  }

  function unregisterTileBodies(owner) {
    const tile = tiles.get(owner);
    if (tile) for (const bodyId of tile.bodyIds) dynBodies.delete(bodyId);
  }

  function applyEvents(events) {
    for (const e of events) {
      switch (e[0]) {
        case "tile_add":
        case "tile_style": {
          const [, owner, ox, oy, statics, dynVisuals, bodies] = e;
          unregisterTileBodies(owner);
          tiles.set(owner, {
            ox, oy,
            statics: statics.map(makeShape),
            dynVisuals: dynVisuals.map(makeShape),
            bodyIds: bodies.map((b) => b[0]),
          });
          for (const [bodyId, shapes] of bodies) dynBodies.set(bodyId, { shapes: shapes.map(makeShape) });
          staticDirty = true;
          break;
        }
        case "tile_remove":
          unregisterTileBodies(e[1]);
          tiles.delete(e[1]);
          staticDirty = true;
          break;
        case "tile_dynvisuals": {
          // Mechanism-driven decorations: refresh geometry without touching
          // the static layer.
          const tile = tiles.get(e[1]);
          if (tile) tile.dynVisuals = e[2].map(makeShape);
          break;
        }
        case "ball_add":
          balls.set(e[1], { r: e[2], fill: css(e[3]), stroke: css(e[4]), paused: !!e[5] });
          break;
        case "ball_style": {
          const ball = balls.get(e[1]);
          if (ball) { ball.fill = css(e[2]); ball.stroke = css(e[3]); ball.paused = !!e[4]; }
          break;
        }
        case "ball_remove":
          balls.delete(e[1]);
          break;
      }
      stats.eventCount++;
    }
  }

  function groupPath(groups, key, style, width) {
    let group = groups.get(key);
    if (!group) {
      group = { style, width, path: new Path2D() };
      groups.set(key, group);
    }
    return group;
  }

  function segmentPath(path, x1, y1, x2, y2) {
    path.moveTo(x1, y1);
    path.lineTo(x2, y2);
  }

  function circlePath(path, x, y, r) {
    path.moveTo(x + r, y);
    path.arc(x, y, r, 0, TAU);
  }

  function strokeGroups(ctx, groups) {
    for (const group of groups.values()) {
      ctx.strokeStyle = group.style;
      ctx.lineWidth = group.width;
      ctx.stroke(group.path);
    }
  }

  function fillGroups(ctx, groups) {
    for (const group of groups.values()) {
      ctx.fillStyle = group.style;
      ctx.fill(group.path);
    }
  }

  function tileVisible(tile, vx, vy, vw, vh) {
    return tile.ox + TILE >= vx && tile.ox <= vx + vw && tile.oy + TILE >= vy && tile.oy <= vy + vh;
  }

  function renderStatic() {
    const w = staticCanvas.width, h = staticCanvas.height;
    const zoom = vp.zoom;
    const vw = w / zoom, vh = h / zoom;
    const vx = vp.x, vy = vp.y;
    sctx.setTransform(1, 0, 0, 1, 0, 0);
    sctx.clearRect(0, 0, w, h);
    // World-to-screen: scale by zoom, then translate so (vx, vy) is top-left.
    sctx.setTransform(zoom, 0, 0, zoom, -vx * zoom, -vy * zoom);

    sctx.fillStyle = PAPER;
    sctx.fillRect(vx, vy, vw, vh);
    const gradient = sctx.createRadialGradient(vx + vw * .5, vy + vh * .45, 0, vx + vw * .5, vy + vh * .45, Math.max(vw, vh) * .75);
    gradient.addColorStop(0, "rgba(255,255,255,.08)");
    gradient.addColorStop(1, "rgba(111,76,30,.08)");
    sctx.fillStyle = gradient;
    sctx.fillRect(vx, vy, vw, vh);

    sctx.strokeStyle = GRID;
    sctx.lineWidth = 1;
    sctx.beginPath();
    for (let x = Math.floor(vx / TILE) * TILE; x <= vx + vw + TILE; x += TILE) { sctx.moveTo(x, vy); sctx.lineTo(x, vy + vh); }
    for (let y = Math.floor(vy / TILE) * TILE; y <= vy + vh + TILE; y += TILE) { sctx.moveTo(vx, y); sctx.lineTo(vx + vw, y); }
    sctx.stroke();

    // Static tile geometry, batched by (color, width) across all visible
    // tiles: all stroke halos below all fills, so joints stay clean.
    const halos = new Map();
    const fills = new Map();
    const circleHalos = new Map();
    const circleFills = new Map();
    const polys = [];
    for (const tile of tiles.values()) {
      if (!tileVisible(tile, vx, vy, vw, vh)) continue;
      const ox = tile.ox, oy = tile.oy;
      for (const s of tile.statics) {
        if (s.t === 0) {
          if (s.stroke) segmentPath(groupPath(halos, `${s.stroke}|${s.r}`, s.stroke, Math.max(3, s.r * 2 + 2)).path, ox + s.x1, oy + s.y1, ox + s.x2, oy + s.y2);
          if (s.fill) segmentPath(groupPath(fills, `${s.fill}|${s.r}`, s.fill, Math.max(3, s.r * 2)).path, ox + s.x1, oy + s.y1, ox + s.x2, oy + s.y2);
        } else if (s.t === 1) {
          if (s.fill) circlePath(groupPath(circleFills, s.fill, s.fill, 0).path, ox + s.x, oy + s.y, s.r);
          if (s.stroke) circlePath(groupPath(circleHalos, s.stroke, s.stroke, 2).path, ox + s.x, oy + s.y, s.r);
        } else {
          polys.push(s, ox, oy);
        }
      }
    }
    sctx.lineCap = "round";
    strokeGroups(sctx, halos);
    fillGroups(sctx, circleFills);
    strokeGroups(sctx, circleHalos);
    // Segment "fills" are wide strokes in the fill color; filling an open
    // line path would paint nothing.
    strokeGroups(sctx, fills);
    for (let i = 0; i < polys.length; i += 3) drawPoly(sctx, polys[i], polys[i + 1], polys[i + 2]);
  }

  function drawPoly(ctx, s, ox, oy) {
    if (!s.pts.length) return;
    ctx.beginPath();
    ctx.moveTo(ox + s.pts[0], oy + s.pts[1]);
    for (let i = 2; i < s.pts.length; i += 2) ctx.lineTo(ox + s.pts[i], oy + s.pts[i + 1]);
    ctx.closePath();
    if (s.fill) { ctx.fillStyle = s.fill; ctx.fill(); }
    if (s.stroke) { ctx.strokeStyle = s.stroke; ctx.lineWidth = 2; ctx.stroke(); }
  }

  function renderDynamic() {
    const w = dynamicCanvas.width, h = dynamicCanvas.height;
    const zoom = vp.zoom;
    const vw = w / zoom, vh = h / zoom;
    const vx = vp.x, vy = vp.y;
    dctx.setTransform(1, 0, 0, 1, 0, 0);
    dctx.clearRect(0, 0, w, h);
    dctx.setTransform(zoom, 0, 0, zoom, -vx * zoom, -vy * zoom);
    dctx.lineCap = "round";

    // Authored dynamic decorations keep fixed tile-local coordinates.
    for (const tile of tiles.values()) {
      if (!tile.dynVisuals.length || !tileVisible(tile, vx, vy, vw, vh)) continue;
      for (const s of tile.dynVisuals) {
        if (s.stroke) { dctx.strokeStyle = s.stroke; dctx.lineWidth = Math.max(2, s.r * 2 + 2); dctx.beginPath(); segmentPath(dctx, tile.ox + s.x1, tile.oy + s.y1, tile.ox + s.x2, tile.oy + s.y2); dctx.stroke(); }
        if (s.fill) { dctx.strokeStyle = s.fill; dctx.lineWidth = Math.max(2, s.r * 2); dctx.beginPath(); segmentPath(dctx, tile.ox + s.x1, tile.oy + s.y1, tile.ox + s.x2, tile.oy + s.y2); dctx.stroke(); }
      }
    }

    // Tile-owned dynamic/kinematic bodies, transformed by the pose stream.
    for (let i = 0; i < poseCount; i++) {
      const record = dynBodies.get(poseId(i));
      if (!record) continue;
      const px = poseFloats[3 * i], py = poseFloats[3 * i + 1], angle = poseFloats[3 * i + 2];
      const c = Math.cos(angle), s = Math.sin(angle);
      for (const shape of record.shapes) {
        if (shape.t === 0) {
          const x1 = px + shape.x1 * c - shape.y1 * s, y1 = py + shape.x1 * s + shape.y1 * c;
          const x2 = px + shape.x2 * c - shape.y2 * s, y2 = py + shape.x2 * s + shape.y2 * c;
          if (shape.stroke) { dctx.strokeStyle = shape.stroke; dctx.lineWidth = Math.max(2, shape.r * 2 + 2); dctx.beginPath(); segmentPath(dctx, x1, y1, x2, y2); dctx.stroke(); }
          if (shape.fill) { dctx.strokeStyle = shape.fill; dctx.lineWidth = Math.max(2, shape.r * 2); dctx.beginPath(); segmentPath(dctx, x1, y1, x2, y2); dctx.stroke(); }
        } else if (shape.t === 1) {
          const cx = px + shape.x * c - shape.y * s, cy = py + shape.x * s + shape.y * c;
          dctx.beginPath(); dctx.arc(cx, cy, shape.r, 0, TAU);
          if (shape.fill) { dctx.fillStyle = shape.fill; dctx.fill(); }
          if (shape.stroke) { dctx.strokeStyle = shape.stroke; dctx.lineWidth = 2; dctx.stroke(); }
        } else {
          const pts = shape.pts;
          dctx.beginPath();
          for (let j = 0; j + 1 < pts.length; j += 2) {
            const lx = px + pts[j] * c - pts[j + 1] * s, ly = py + pts[j] * s + pts[j + 1] * c;
            if (j === 0) dctx.moveTo(lx, ly); else dctx.lineTo(lx, ly);
          }
          dctx.closePath();
          if (shape.fill) { dctx.fillStyle = shape.fill; dctx.fill(); }
          if (shape.stroke) { dctx.strokeStyle = shape.stroke; dctx.lineWidth = 2; dctx.stroke(); }
        }
      }
    }

    // Balls, batched into one path per color group.
    const groups = new Map();
    for (let i = 0; i < poseCount; i++) {
      const ball = balls.get(poseId(i));
      if (!ball || ball.paused) continue;
      const x = poseFloats[3 * i], y = poseFloats[3 * i + 1];
      if (x < vx - ball.r || x > vx + vw + ball.r || y < vy - ball.r || y > vy + vh + ball.r) continue;
      const key = `${ball.fill}|${ball.stroke}`;
      let group = groups.get(key);
      if (!group) { group = { fill: ball.fill, stroke: ball.stroke, path: new Path2D() }; groups.set(key, group); }
      circlePath(group.path, x, y, ball.r);
    }
    for (const group of groups.values()) {
      if (group.fill) { dctx.fillStyle = group.fill; dctx.fill(group.path); }
      if (group.stroke) { dctx.strokeStyle = group.stroke; dctx.lineWidth = 2; dctx.stroke(group.path); }
    }
  }

  function poseId(i) {
    return poseStride === 1 ? poseIds[i] : poseIds[2 * i] + poseIds[2 * i + 1] * 4294967296;
  }

  window.EbmScene = {
    attach(staticEl, dynamicEl) {
      staticCanvas = staticEl;
      dynamicCanvas = dynamicEl;
      sctx = staticCanvas.getContext("2d");
      dctx = dynamicCanvas.getContext("2d");
      staticDirty = true;
    },

    frame(events, x, y, zoom, ids, floats, idStride) {
      if (events.length) applyEvents(events);
      poseIds = ids;
      poseFloats = floats;
      poseStride = idStride || 1;
      poseCount = idStride === 1 ? ids.length : Math.floor(ids.length / (idStride || 1));
      if (x !== vp.x || y !== vp.y || zoom !== vp.zoom) {
        vp = { x, y, zoom };
        staticDirty = true;
      }
      // Python-side resize reassigns canvas.width, which clears the bitmap.
      if (staticCanvas.width !== lastW || staticCanvas.height !== lastH) {
        lastW = staticCanvas.width;
        lastH = staticCanvas.height;
        staticDirty = true;
      }

      if (staticDirty) {
        const started = performance.now();
        renderStatic();
        const elapsed = performance.now() - started;
        stats.staticFrames++;
        stats.staticTotalMs += elapsed;
        stats.staticMaxMs = Math.max(stats.staticMaxMs, elapsed);
        staticDirty = false;
      }
      // A stable 30 FPS dynamic cadence composites far better in Firefox than
      // an uneven 40-60 FPS; physics still advances every animation frame.
      const now = performance.now();
      if (now - lastDynamic >= DYNAMIC_INTERVAL) {
        renderDynamic();
        const elapsed = performance.now() - now;
        stats.dynamicFrames++;
        stats.dynamicTotalMs += elapsed;
        stats.dynamicMaxMs = Math.max(stats.dynamicMaxMs, elapsed);
        lastDynamic = now;
      }
    },

    debug() {
      let segs = 0, circles = 0, polys = 0, dynVis = 0;
      for (const tile of tiles.values()) {
        for (const s of tile.statics) { if (s.t === 0) segs++; else if (s.t === 1) circles++; else polys++; }
        dynVis += tile.dynVisuals.length;
      }
      return { tiles: tiles.size, segs, circles, polys, dynVis, dynBodies: dynBodies.size, balls: balls.size, vp };
    },

    consumeStats() {
      const snapshot = {
        ...stats,
        tiles: tiles.size,
        balls: balls.size,
        bodies: poseCount,
      };
      stats.staticFrames = 0; stats.staticTotalMs = 0; stats.staticMaxMs = 0;
      stats.dynamicFrames = 0; stats.dynamicTotalMs = 0; stats.dynamicMaxMs = 0;
      stats.eventCount = 0;
      return snapshot;
    },
  };
})();
