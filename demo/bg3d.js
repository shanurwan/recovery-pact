// Background scene: the incident itself, in 3D, kept quiet enough to read over.
// Globe of dots = the database. Orbits = Database AI (blue), Business AI (green),
// Safety authority (amber). Comets = checkouts arriving. Floor = a slow field of
// traffic. window.rpScene.setHealth(0..1) is driven by the replay: as checkout
// fails, the scene warms to red and the field turns choppy.
"use strict";

(function () {
  const canvas = document.getElementById("bg");
  if (!canvas || !window.THREE) return;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const THREE = window.THREE;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
  } catch (e) {
    canvas.remove();
    return;
  }
  const small = window.innerWidth < 760;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, small ? 1.25 : 1.75));

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x07080c, 0.03);
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 120);

  const C = {
    ink: new THREE.Color(0xc9d3e6),
    ok: new THREE.Color(0x84c441),
    bad: new THREE.Color(0xf2645a),
    db: new THREE.Color(0x8ab4f8),
    gate: new THREE.Color(0xe9b44c),
  };

  function dotTexture() {
    const c = document.createElement("canvas");
    c.width = c.height = 64;
    const g = c.getContext("2d");
    const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grd.addColorStop(0, "rgba(255,255,255,1)");
    grd.addColorStop(0.3, "rgba(255,255,255,0.7)");
    grd.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = grd;
    g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
  }
  const dot = dotTexture();

  const world = new THREE.Group();
  scene.add(world);

  // The database: an even shell of dots (Fibonacci sphere), lit from one side.
  const GN = small ? 1400 : 2600, R = 2.6;
  const gPos = new Float32Array(GN * 3), gCol = new Float32Array(GN * 3), gBase = new Float32Array(GN);
  for (let i = 0; i < GN; i++) {
    const y = 1 - (i / (GN - 1)) * 2, r = Math.sqrt(1 - y * y), th = i * 2.399963229728653;
    gPos[i * 3] = Math.cos(th) * r * R; gPos[i * 3 + 1] = y * R; gPos[i * 3 + 2] = Math.sin(th) * r * R;
    gBase[i] = 0.5 + 0.8 * Math.max(0, (Math.cos(th) * r * 0.6 + y * 0.5 + 0.55));
  }
  const globeGeo = new THREE.BufferGeometry();
  globeGeo.setAttribute("position", new THREE.BufferAttribute(gPos, 3));
  globeGeo.setAttribute("color", new THREE.BufferAttribute(gCol, 3));
  const globe = new THREE.Points(globeGeo, new THREE.PointsMaterial({
    size: small ? 0.12 : 0.1, map: dot, vertexColors: true, transparent: true, opacity: 1,
    depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  world.add(globe);
  // A dark core so the back of the shell reads as depth, not noise.
  const core = new THREE.Mesh(new THREE.SphereGeometry(R * 0.97, 48, 48), new THREE.MeshBasicMaterial({ color: 0x07080c, transparent: true, opacity: 0.55 }));
  world.add(core);
  const halo = new THREE.Mesh(new THREE.SphereGeometry(R * 1.35, 48, 48), new THREE.MeshBasicMaterial({ color: 0x1a2a4a, transparent: true, opacity: 0.22, depthWrite: false, blending: THREE.AdditiveBlending }));
  world.add(halo);

  // Orbits: thin lines, each with a small beacon.
  function orbit(radius, color, tilt, opacity) {
    const pts = [];
    for (let k = 0; k <= 256; k++) { const a = (k / 256) * Math.PI * 2; pts.push(new THREE.Vector3(Math.cos(a) * radius, 0, Math.sin(a) * radius)); }
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color, transparent: true, opacity }));
    const g = new THREE.Group();
    g.rotation.set(tilt[0], tilt[1], tilt[2]);
    g.add(line);
    const b = new THREE.Mesh(new THREE.SphereGeometry(0.06, 16, 16), new THREE.MeshBasicMaterial({ color }));
    const glowB = new THREE.Sprite(new THREE.SpriteMaterial({ map: dot, color, transparent: true, opacity: 0.9, depthWrite: false, blending: THREE.AdditiveBlending }));
    glowB.scale.setScalar(0.55);
    b.add(glowB);
    g.add(b);
    world.add(g);
    return { g, line, b, radius };
  }
  const oDb = orbit(3.5, C.db, [0.42, 0, 0.18], 0.4);
  const oBiz = orbit(4.1, C.ok, [-0.3, 0, -0.32], 0.36);
  const oGate = orbit(4.9, C.gate, [0.08, 0, 0.04], 0.22);

  // Checkouts: comets that arrive from the far field and land on the globe.
  const PN = small ? 260 : 520;
  const pPos = new Float32Array(PN * 3), pCol = new Float32Array(PN * 3);
  const pFrom = new Float32Array(PN * 3), pProg = new Float32Array(PN), pSpd = new Float32Array(PN), pFail = new Uint8Array(PN);
  function spawn(i) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, r = 12 + Math.random() * 8, s = Math.sqrt(1 - u * u);
    pFrom[i * 3] = r * s * Math.cos(th); pFrom[i * 3 + 1] = r * u * 0.5; pFrom[i * 3 + 2] = r * s * Math.sin(th);
    pProg[i] = 0; pSpd[i] = 0.05 + Math.random() * 0.06;
  }
  for (let i = 0; i < PN; i++) { spawn(i); pProg[i] = Math.random(); }
  const pGeo = new THREE.BufferGeometry();
  pGeo.setAttribute("position", new THREE.BufferAttribute(pPos, 3));
  pGeo.setAttribute("color", new THREE.BufferAttribute(pCol, 3));
  world.add(new THREE.Points(pGeo, new THREE.PointsMaterial({
    size: small ? 0.2 : 0.17, map: dot, vertexColors: true, transparent: true, opacity: 0.9, depthWrite: false, blending: THREE.AdditiveBlending,
  })));

  // Floor: a wide field of dots rolling in slow waves.
  const FX = small ? 70 : 120, FZ = small ? 40 : 60, SP = 0.55;
  const FN = FX * FZ;
  const fPos = new Float32Array(FN * 3), fCol = new Float32Array(FN * 3);
  for (let x = 0; x < FX; x++) for (let z = 0; z < FZ; z++) {
    const i = x * FZ + z;
    fPos[i * 3] = (x - FX / 2) * SP; fPos[i * 3 + 1] = 0; fPos[i * 3 + 2] = -z * SP + 8;
  }
  const fGeo = new THREE.BufferGeometry();
  fGeo.setAttribute("position", new THREE.BufferAttribute(fPos, 3));
  fGeo.setAttribute("color", new THREE.BufferAttribute(fCol, 3));
  const floor = new THREE.Points(fGeo, new THREE.PointsMaterial({
    size: 0.09, map: dot, vertexColors: true, transparent: true, opacity: 1, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  floor.position.y = -3.6;
  scene.add(floor);

  let health = 1, target = 1;
  const tmp = new THREE.Color(), tint = new THREE.Color();

  let wide = true;
  function resize() {
    const w = window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    // Wide screens: the globe sits to the right of the reading column. Narrow: behind it, smaller.
    wide = w / h > 1.15 && w > 900;
    world.position.set(wide ? 5.4 : 0, wide ? 0.6 : 1.6, 0);
    world.scale.setScalar(wide ? 1 : 0.8);
  }
  window.addEventListener("resize", resize);
  resize();

  let scrollT = 0;
  window.addEventListener("scroll", () => {
    const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    scrollT = window.scrollY / max;
  }, { passive: true });

  let mx = 0, my = 0;
  window.addEventListener("pointermove", (e) => {
    mx = (e.clientX / window.innerWidth - 0.5) * 2;
    my = (e.clientY / window.innerHeight - 0.5) * 2;
  }, { passive: true });

  let last = performance.now(), running = true;
  document.addEventListener("visibilitychange", () => {
    running = !document.hidden;
    if (running) { last = performance.now(); requestAnimationFrame(frame); }
  });

  camera.position.set(0, 1.4, small ? 17 : 14);

  function step(dt, t) {
    health += (target - health) * Math.min(1, dt * 2.2);
    const sick = 1 - health;
    tint.copy(C.ink).lerp(C.bad, sick * 0.85);

    // Globe: lit dots, a slow scan band, warming to red as checkout fails.
    for (let i = 0; i < GN; i++) {
      const y = gPos[i * 3 + 1] / R;
      const band = Math.max(0, 1 - Math.abs(y - Math.sin(t * 0.35) * 0.9) * 7);
      const k = gBase[i] * (0.75 + 0.6 * band);
      tmp.copy(C.db).lerp(tint, 0.55 + sick * 0.45).lerp(C.ok, band * 0.35 * health);
      gCol[i * 3] = tmp.r * k; gCol[i * 3 + 1] = tmp.g * k; gCol[i * 3 + 2] = tmp.b * k;
    }
    globeGeo.attributes.color.needsUpdate = true;
    globe.rotation.y += dt * (0.05 + 0.08 * health);
    halo.material.color.setHex(0x1a2a4a).lerp(new THREE.Color(0x4a1418), sick);
    halo.scale.setScalar(1 + Math.sin(t * (health < 0.6 ? 4 : 1.2)) * (health < 0.6 ? 0.04 : 0.015));

    // Orbits and beacons
    const orbits = [[oDb, 0.45], [oBiz, -0.36], [oGate, 0.12]];
    for (const [o, s] of orbits) {
      const a = t * s;
      o.b.position.set(Math.cos(a) * o.radius, 0, Math.sin(a) * o.radius);
    }
    oGate.line.material.opacity = 0.22 + sick * 0.4;
    oDb.g.rotation.y += dt * 0.03;
    oBiz.g.rotation.y -= dt * 0.025;

    // Comets: failing ones stall at the authority's orbit instead of landing.
    const flow = 0.2 + 0.8 * health;
    for (let i = 0; i < PN; i++) {
      pProg[i] += pSpd[i] * dt * flow;
      if (pProg[i] >= 1) { spawn(i); pFail[i] = Math.random() > health ? 1 : 0; }
      const stop = pFail[i] ? 0.72 : 1;
      const p = Math.min(pProg[i], stop);
      if (pFail[i] && pProg[i] > 0.95) spawn(i);
      const e = 1 - Math.pow(1 - p, 2.2);
      const sx = pFrom[i * 3], sy = pFrom[i * 3 + 1], sz = pFrom[i * 3 + 2];
      const len = Math.hypot(sx, sy, sz), end = (R * 1.02) / len;
      const f = 1 - e * (1 - end);
      const sw = (1 - e) * 0.9;
      const cs = Math.cos(sw), sn = Math.sin(sw);
      const x = sx * f, z = sz * f;
      pPos[i * 3] = x * cs - z * sn; pPos[i * 3 + 1] = sy * f; pPos[i * 3 + 2] = x * sn + z * cs;
      tmp.copy(pFail[i] ? C.bad : C.ok).lerp(C.ink, pFail[i] ? 0 : 0.35);
      const fade = Math.min(1, p * 3) * (pFail[i] ? 1 : 1 - Math.max(0, (p - 0.92) / 0.08));
      pCol[i * 3] = tmp.r * fade; pCol[i * 3 + 1] = tmp.g * fade; pCol[i * 3 + 2] = tmp.b * fade;
    }
    pGeo.attributes.position.needsUpdate = true;
    pGeo.attributes.color.needsUpdate = true;

    // Floor waves: calm when healthy, choppy when failing.
    const amp = 0.35 + sick * 0.55, fr = 0.55 + sick * 0.5;
    for (let i = 0; i < FN; i++) {
      const x = fPos[i * 3], z = fPos[i * 3 + 2];
      const yv = Math.sin(x * 0.28 * fr + t * 0.5) * Math.cos(z * 0.22 * fr + t * 0.35) * amp
        + Math.sin((x + z) * 0.12 + t * 0.25) * amp * 0.6;
      fPos[i * 3 + 1] = yv;
      const k = 0.35 + Math.max(0, yv / (amp * 1.6)) * 0.8;
      tmp.copy(C.db).lerp(tint, 0.5 + sick * 0.5);
      fCol[i * 3] = tmp.r * k; fCol[i * 3 + 1] = tmp.g * k; fCol[i * 3 + 2] = tmp.b * k;
    }
    fGeo.attributes.position.needsUpdate = true;
    fGeo.attributes.color.needsUpdate = true;

    // Camera drifts with the pointer; scrolling turns the world and lowers the view.
    camera.position.x += (mx * 0.9 - camera.position.x) * dt * 0.8;
    camera.position.y += (1.4 - my * 0.6 - scrollT * 1.2 - camera.position.y) * dt * 0.8;
    world.rotation.y += ((scrollT * Math.PI * 0.9) - world.rotation.y) * dt * 1.5;
    world.rotation.x += ((0.18 + scrollT * 0.25) - world.rotation.x) * dt * 1.5;
    camera.lookAt(wide ? 2.2 : 0, 0, 0);
  }

  function frame(now) {
    if (!running) return;
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    step(dt, now / 1000);
    renderer.render(scene, camera);
    if (!reduced) requestAnimationFrame(frame);
  }

  // Reduced motion: settle the scene and draw one still frame.
  if (reduced) {
    for (let k = 0; k < 120; k++) step(1 / 30, k / 30);
    renderer.render(scene, camera);
  } else {
    requestAnimationFrame(frame);
  }

  window.rpScene = {
    setHealth(h) {
      target = Math.max(0, Math.min(1, h));
      if (reduced) { for (let k = 0; k < 60; k++) step(1 / 30, k / 30); renderer.render(scene, camera); }
    },
  };
})();
