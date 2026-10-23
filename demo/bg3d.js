// Background scene: the incident itself, in 3D.
// Core = the database. Particles = checkouts flowing in (green when they succeed,
// red and stalled when they fail). Rings = Database AI (blue), Business AI (green),
// Safety authority (amber). window.rpScene.setHealth(0..1) is driven by the replay.
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
  scene.fog = new THREE.FogExp2(0x08090b, 0.045);
  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 100);
  camera.position.set(0, 1.2, small ? 15 : 12);

  const world = new THREE.Group();
  scene.add(world);

  // Soft round particle sprite (points are square without a texture).
  function dotTexture() {
    const c = document.createElement("canvas");
    c.width = c.height = 64;
    const g = c.getContext("2d");
    const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grd.addColorStop(0, "rgba(255,255,255,1)");
    grd.addColorStop(0.35, "rgba(255,255,255,0.65)");
    grd.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = grd;
    g.fillRect(0, 0, 64, 64);
    const t = new THREE.CanvasTexture(c);
    return t;
  }
  const dot = dotTexture();

  const C = {
    ok: new THREE.Color(0x76b900),
    bad: new THREE.Color(0xff5f57),
    db: new THREE.Color(0x7ea6d8),
    biz: new THREE.Color(0x76b900),
    gate: new THREE.Color(0xf2b441),
  };

  // Core: the database
  const core = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.15, 2),
    new THREE.MeshBasicMaterial({ color: 0x7ea6d8, wireframe: true, transparent: true, opacity: 0.55 })
  );
  world.add(core);
  const glow = new THREE.Mesh(
    new THREE.SphereGeometry(0.85, 32, 32),
    new THREE.MeshBasicMaterial({ color: 0x1d2a12, transparent: true, opacity: 0.55 })
  );
  world.add(glow);

  // Rings: two guardians and the authority around them
  function ring(radius, color, tilt, width, opacity) {
    const m = new THREE.Mesh(
      new THREE.TorusGeometry(radius, width, 8, 160),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity })
    );
    m.rotation.x = tilt[0];
    m.rotation.y = tilt[1];
    world.add(m);
    return m;
  }
  const ringDb = ring(2.3, C.db, [1.15, 0.25], 0.018, 0.75);
  const ringBiz = ring(2.75, C.biz, [1.75, -0.35], 0.018, 0.75);
  const ringGate = ring(3.6, C.gate, [Math.PI / 2, 0], 0.01, 0.45);

  // Guardian beacons riding their rings
  function beacon(color) {
    const b = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 16), new THREE.MeshBasicMaterial({ color }));
    world.add(b);
    return b;
  }
  const bDb = beacon(C.db);
  const bBiz = beacon(C.biz);

  // Checkout particles: born on a far shell, travel to the core
  const N = small ? 900 : 1800;
  const pos = new Float32Array(N * 3);
  const col = new Float32Array(N * 3);
  const start = new Float32Array(N * 3);
  const prog = new Float32Array(N);
  const speed = new Float32Array(N);
  function respawn(i) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, r = 9 + Math.random() * 6;
    const s = Math.sqrt(1 - u * u);
    start[i * 3] = r * s * Math.cos(th);
    start[i * 3 + 1] = r * u * 0.6;
    start[i * 3 + 2] = r * s * Math.sin(th);
    prog[i] = Math.random() * 0.15;
    speed[i] = 0.06 + Math.random() * 0.08;
  }
  for (let i = 0; i < N; i++) { respawn(i); prog[i] = Math.random(); }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
  const points = new THREE.Points(geo, new THREE.PointsMaterial({
    size: small ? 0.16 : 0.14, map: dot, alphaTest: 0.01, vertexColors: true, transparent: true, opacity: 0.9, depthWrite: false,
    blending: THREE.AdditiveBlending,
  }));
  world.add(points);

  // Far starfield for depth
  const starGeo = new THREE.BufferGeometry();
  const sp = new Float32Array(600 * 3);
  for (let i = 0; i < 600; i++) {
    sp[i * 3] = (Math.random() - 0.5) * 80;
    sp[i * 3 + 1] = (Math.random() - 0.5) * 50;
    sp[i * 3 + 2] = -10 - Math.random() * 40;
  }
  starGeo.setAttribute("position", new THREE.BufferAttribute(sp, 3));
  scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({ size: 0.12, map: dot, color: 0x9aa0a6, transparent: true, opacity: 0.45, depthWrite: false })));

  // Health 1 = flowing and green; 0 = stalled and red. Eased toward the target.
  let health = 1, target = 1;
  const tmp = new THREE.Color();

  function resize() {
    const w = window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    // Centred behind the whole page; slightly smaller on portrait screens.
    world.position.set(0, 0, 0);
    world.scale.setScalar(w / h > 1 ? 1.75 : 1.1);
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

  function step(dt, t) {
    health += (target - health) * Math.min(1, dt * 2.2);
    const flow = 0.18 + 0.82 * health; // stalled traffic barely moves
    for (let i = 0; i < N; i++) {
      // Failing checkouts queue up just outside the authority ring instead of reaching the core.
      const limit = 1 - (1 - health) * 0.62;
      prog[i] += speed[i] * dt * flow;
      if (prog[i] >= 1 || (health < 0.5 && prog[i] > limit && Math.random() < 0.002)) respawn(i);
      const p = Math.min(prog[i], limit + (prog[i] > limit ? (prog[i] - limit) * 0.05 : 0));
      const e = p * p * (3 - 2 * p);
      const swirl = (1 - e) * 1.4 + t * 0.15;
      const sx = start[i * 3], sy = start[i * 3 + 1], sz = start[i * 3 + 2];
      const cx = sx * (1 - e), cy = sy * (1 - e), cz = sz * (1 - e);
      const cs = Math.cos(swirl * 0.35), sn = Math.sin(swirl * 0.35);
      pos[i * 3] = cx * cs - cz * sn;
      pos[i * 3 + 1] = cy;
      pos[i * 3 + 2] = cx * sn + cz * cs;
      const failing = Math.random() > health ? 1 : 0;
      tmp.copy(C.ok).lerp(C.bad, failing ? 0.95 : (1 - health) * 0.35);
      const fade = 0.35 + 0.65 * Math.min(1, e * 1.6);
      col[i * 3] = tmp.r * fade; col[i * 3 + 1] = tmp.g * fade; col[i * 3 + 2] = tmp.b * fade;
    }
    geo.attributes.position.needsUpdate = true;
    geo.attributes.color.needsUpdate = true;

    core.rotation.y += dt * (0.15 + 0.35 * health);
    core.rotation.x += dt * 0.05;
    core.material.color.copy(C.db).lerp(C.bad, (1 - health) * 0.8);
    glow.material.color.setHex(0x1d2a12).lerp(new THREE.Color(0x5a1420), (1 - health) * 0.9);
    const pulse = 1 + Math.sin(t * (health < 0.6 ? 6 : 1.6)) * (health < 0.6 ? 0.06 : 0.025);
    glow.scale.setScalar(pulse);
    ringDb.rotation.z += dt * 0.35;
    ringBiz.rotation.z -= dt * 0.28;
    ringGate.rotation.z += dt * 0.06;
    ringGate.material.opacity = 0.35 + (1 - health) * 0.4;
    const a = t * 0.9, b = -t * 0.7;
    bDb.position.set(Math.cos(a) * 2.3, Math.sin(a) * 2.3 * Math.cos(1.15), Math.sin(a) * 2.3 * Math.sin(1.15));
    bBiz.position.set(Math.cos(b) * 2.75, Math.sin(b) * 2.75 * Math.cos(1.75), Math.sin(b) * 2.75 * Math.sin(1.75));
    camera.position.x += (mx * 1.2 - camera.position.x) * dt * 0.8;
    camera.position.y += (1.2 - my * 0.8 - camera.position.y) * dt * 0.8;
    world.rotation.y += ((scrollT * Math.PI * 1.2) - world.rotation.y) * dt * 1.5;
    world.rotation.x += ((scrollT * 0.5) - world.rotation.x) * dt * 1.5;
    camera.lookAt(0, 0, 0);
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
