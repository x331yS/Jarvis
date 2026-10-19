// Holographic arc-reactor scene for the JARVIS HUD (Three.js, WebGL).
// Reacts to the body's `state-*` class set by main.js. When WebGL or Three.js
// is unavailable the page keeps the CSS reactor (`no-webgl` body class).
(() => {
    const canvas = document.getElementById("space");
    const reactorSlot = document.querySelector(".reactor");

    function fallBack(reason) {
        document.body.classList.remove("webgl-ready");
        document.body.classList.add("no-webgl");
        console.warn("JARVIS HUD: 3D scene unavailable:", reason);
    }

    if (typeof THREE === "undefined") {
        fallBack("Three.js not loaded");
        return;
    }

    let renderer;
    try {
        const attributes = {alpha: false, antialias: true, powerPreference: "default"};
        const context = canvas.getContext("webgl2", attributes) || canvas.getContext("webgl", attributes);
        if (!context) throw new Error("WebGL context unavailable");
        renderer = new THREE.WebGLRenderer({
            canvas,
            context,
            antialias: true,
            alpha: false,
            powerPreference: "default"
        });
    } catch (error) {
        fallBack(error);
        return;
    }

    renderer.setClearColor(0x02060b, 1);
    document.body.classList.add("webgl-ready");
    let contextLost = false;
    canvas.addEventListener("webglcontextlost", event => {
        event.preventDefault();
        contextLost = true;
        fallBack("WebGL context lost");
    });
    canvas.addEventListener("webglcontextrestored", () => {
        contextLost = false;
        document.body.classList.remove("no-webgl");
        document.body.classList.add("webgl-ready");
        layout();
    });

    // World radius of the outer reactor ring; layout() maps it onto the
    // on-screen reactor slot so the HTML label/waveform stay around it.
    const REACTOR_RADIUS = 3.4;

    const STATES = {
        idle:      { color: 0x62e6ff, spin: 1.0, pulse: 1.1, wave: 0.18, glow: 0.85 },
        listening: { color: 0x9af6ff, spin: 1.7, pulse: 2.8, wave: 0.65, glow: 1.1 },
        thinking:  { color: 0x4f9dff, spin: 3.4, pulse: 2.0, wave: 0.3,  glow: 1.0 },
        executing: { color: 0x5effd2, spin: 2.6, pulse: 2.4, wave: 0.4,  glow: 1.0 },
        speaking:  { color: 0xc4f9ff, spin: 1.9, pulse: 3.6, wave: 1.0,  glow: 1.25 },
        error:     { color: 0xff5a4f, spin: 0.6, pulse: 4.5, wave: 0.2,  glow: 1.0 }
    };

    const live = {
        color: new THREE.Color(STATES.idle.color),
        spin: STATES.idle.spin,
        pulse: STATES.idle.pulse,
        wave: STATES.idle.wave,
        glow: STATES.idle.glow
    };
    const targetColor = new THREE.Color();

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x02060b, 30, 90);
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 300);

    const tinted = [];

    function track(material, baseOpacity) {
        material.userData.baseOpacity = baseOpacity;
        tinted.push(material);
        return material;
    }

    function glowMaterial(opacity, fog = false) {
        return track(new THREE.MeshBasicMaterial({
            color: live.color,
            transparent: true,
            opacity,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
            side: THREE.DoubleSide,
            fog
        }), opacity);
    }

    function lineMaterial(opacity, fog = false) {
        return track(new THREE.LineBasicMaterial({
            color: live.color,
            transparent: true,
            opacity,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
            fog
        }), opacity);
    }

    function radialTexture(stops) {
        const size = 128;
        const surface = document.createElement("canvas");
        surface.width = surface.height = size;
        const ctx = surface.getContext("2d");
        const gradient = ctx.createRadialGradient(
            size / 2, size / 2, 0, size / 2, size / 2, size / 2
        );
        for (const [offset, colour] of stops) {
            gradient.addColorStop(offset, colour);
        }
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, size, size);
        return new THREE.CanvasTexture(surface);
    }

    const glowTexture = radialTexture([
        [0, "rgba(255,255,255,1)"],
        [0.18, "rgba(255,255,255,0.65)"],
        [0.5, "rgba(255,255,255,0.14)"],
        [1, "rgba(255,255,255,0)"]
    ]);
    const dotTexture = radialTexture([
        [0, "rgba(255,255,255,1)"],
        [0.35, "rgba(255,255,255,0.55)"],
        [1, "rgba(255,255,255,0)"]
    ]);

    function glowSprite(scale, opacity) {
        const sprite = new THREE.Sprite(track(new THREE.SpriteMaterial({
            map: glowTexture,
            color: live.color,
            transparent: true,
            opacity,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }), opacity));
        sprite.scale.setScalar(scale);
        return sprite;
    }

    function circlePoints(radius, segments) {
        const points = [];
        for (let i = 0; i < segments; i++) {
            const angle = (i / segments) * Math.PI * 2;
            points.push(new THREE.Vector3(
                Math.cos(angle) * radius, Math.sin(angle) * radius, 0
            ));
        }
        return points;
    }

    // ---- Arc reactor -------------------------------------------------------
    const reactor = new THREE.Group();
    reactor.rotation.x = -0.18;
    scene.add(reactor);

    const core = new THREE.Mesh(
        new THREE.SphereGeometry(0.42, 32, 32),
        new THREE.MeshBasicMaterial({ color: 0xeaffff, fog: false })
    );
    reactor.add(core);

    const coreGlow = glowSprite(3.0, 0.95);
    const halo = glowSprite(8.5, 0.32);
    reactor.add(coreGlow, halo);

    const innerRing = new THREE.Mesh(
        new THREE.TorusGeometry(0.72, 0.035, 8, 96),
        glowMaterial(0.9)
    );
    reactor.add(innerRing);

    const segments = new THREE.Group();
    const segmentCount = 10;
    for (let i = 0; i < segmentCount; i++) {
        const span = (Math.PI * 2) / segmentCount;
        segments.add(new THREE.Mesh(
            new THREE.RingGeometry(1.05, 1.42, 10, 1, i * span, span * 0.72),
            glowMaterial(0.32)
        ));
    }
    reactor.add(segments);

    const coil = new THREE.Mesh(
        new THREE.TorusGeometry(1.58, 0.022, 6, 160),
        glowMaterial(0.75)
    );
    reactor.add(coil);

    const tickPositions = [];
    const tickCount = 120;
    for (let i = 0; i < tickCount; i++) {
        const angle = (i / tickCount) * Math.PI * 2;
        const inner = 1.82;
        const outer = i % 5 === 0 ? 2.02 : 1.92;
        tickPositions.push(
            Math.cos(angle) * inner, Math.sin(angle) * inner, 0,
            Math.cos(angle) * outer, Math.sin(angle) * outer, 0
        );
    }
    const tickGeometry = new THREE.BufferGeometry();
    tickGeometry.setAttribute(
        "position", new THREE.Float32BufferAttribute(tickPositions, 3)
    );
    const ticks = new THREE.LineSegments(tickGeometry, lineMaterial(0.55));
    reactor.add(ticks);

    const arcs = [
        { radius: 2.35, arc: Math.PI * 1.2, speed: 0.55, opacity: 0.85 },
        { radius: 2.65, arc: Math.PI * 0.55, speed: -0.9, opacity: 0.7 },
        { radius: 2.95, arc: Math.PI * 1.55, speed: 0.32, opacity: 0.5 }
    ].map(({ radius, arc, speed, opacity }) => {
        const mesh = new THREE.Mesh(
            new THREE.TorusGeometry(radius, 0.028, 6, 160, arc),
            glowMaterial(opacity)
        );
        mesh.userData.speed = speed;
        reactor.add(mesh);
        return mesh;
    });

    const outerRing = new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints(circlePoints(REACTOR_RADIUS, 256)),
        lineMaterial(0.45)
    );
    reactor.add(outerRing);

    const brackets = new THREE.Group();
    for (let i = 0; i < 4; i++) {
        const bracket = new THREE.Mesh(
            new THREE.RingGeometry(
                REACTOR_RADIUS + 0.12, REACTOR_RADIUS + 0.26, 24, 1,
                i * Math.PI / 2 - 0.22, 0.44
            ),
            glowMaterial(0.6)
        );
        brackets.add(bracket);
    }
    reactor.add(brackets);

    // Radial voice bars between the coil and the arcs.
    const barCount = 128;
    const barPositions = new Float32Array(barCount * 6);
    const barGeometry = new THREE.BufferGeometry();
    barGeometry.setAttribute(
        "position",
        new THREE.BufferAttribute(barPositions, 3).setUsage(THREE.DynamicDrawUsage)
    );
    reactor.add(new THREE.LineSegments(barGeometry, lineMaterial(0.8)));

    const pulseRing = new THREE.Mesh(
        new THREE.RingGeometry(0.97, 1.0, 128),
        glowMaterial(0.0)
    );
    reactor.add(pulseRing);

    // ---- Holographic globe -------------------------------------------------
    const globe = new THREE.Group();
    globe.rotation.set(0.42, 0, 0.2);
    scene.add(globe);

    const globeGeometry = new THREE.IcosahedronGeometry(REACTOR_RADIUS * 1.32, 3);
    globe.add(new THREE.LineSegments(
        new THREE.EdgesGeometry(globeGeometry),
        lineMaterial(0.07)
    ));
    globe.add(new THREE.Points(
        globeGeometry,
        track(new THREE.PointsMaterial({
            color: live.color,
            map: dotTexture,
            size: 0.09,
            transparent: true,
            opacity: 0.35,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }), 0.35)
    ));

    // ---- Orbiting satellites ----------------------------------------------
    const orbits = [
        { radius: REACTOR_RADIUS * 1.55, tilt: 1.1, yaw: 0.3, speed: 0.35 },
        { radius: REACTOR_RADIUS * 1.75, tilt: -0.9, yaw: -0.6, speed: -0.22 }
    ].map(({ radius, tilt, yaw, speed }) => {
        const pivot = new THREE.Group();
        pivot.rotation.set(tilt, yaw, 0);
        pivot.add(new THREE.LineLoop(
            new THREE.BufferGeometry().setFromPoints(circlePoints(radius, 200)),
            lineMaterial(0.12)
        ));
        const satellite = glowSprite(0.9, 0.9);
        pivot.add(satellite);
        scene.add(pivot);
        return { pivot, satellite, radius, speed, angle: Math.random() * Math.PI * 2 };
    });

    // ---- Floor grid and drifting dust -------------------------------------
    const grid = new THREE.GridHelper(120, 80);
    grid.material = lineMaterial(0.09, true);
    grid.position.y = -REACTOR_RADIUS * 2.2;
    scene.add(grid);

    const dustCount = 1400;
    const dustPositions = new Float32Array(dustCount * 3);
    const dustSpeeds = new Float32Array(dustCount);
    for (let i = 0; i < dustCount; i++) {
        dustPositions[i * 3] = (Math.random() - 0.5) * 90;
        dustPositions[i * 3 + 1] = (Math.random() - 0.5) * 70;
        dustPositions[i * 3 + 2] = -5 - Math.random() * 70;
        dustSpeeds[i] = 0.4 + Math.random() * 1.4;
    }
    const dustGeometry = new THREE.BufferGeometry();
    dustGeometry.setAttribute(
        "position",
        new THREE.BufferAttribute(dustPositions, 3).setUsage(THREE.DynamicDrawUsage)
    );
    scene.add(new THREE.Points(
        dustGeometry,
        track(new THREE.PointsMaterial({
            color: live.color,
            map: dotTexture,
            size: 0.35,
            transparent: true,
            opacity: 0.55,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }), 0.55)
    ));

    // ---- Layout ------------------------------------------------------------
    let baseCameraZ = 30;

    function layout() {
        const width = window.innerWidth;
        const height = window.innerHeight;
        if (!width || !height) {
            return;
        }

        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
        renderer.setSize(width, height, false);

        const radiusPx = Math.min(width, height) * 0.24;
        if (reactorSlot) {
            const diameter = `${Math.round(radiusPx * 2)}px`;
            reactorSlot.style.width = diameter;
            reactorSlot.style.height = diameter;
        }

        camera.aspect = width / height;
        const halfHeightWorld = REACTOR_RADIUS * (height / 2) / radiusPx;
        baseCameraZ = halfHeightWorld / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
        scene.fog.near = baseCameraZ + 4;
        scene.fog.far = baseCameraZ + 80;

        // Shift the projection so the world origin lands on the reactor slot.
        let offsetY = 0;
        if (reactorSlot) {
            const rect = reactorSlot.getBoundingClientRect();
            offsetY = rect.top + rect.height / 2 - height / 2;
        }
        camera.setViewOffset(width, height, 0, -offsetY, width, height);
        camera.updateProjectionMatrix();
    }

    window.addEventListener("resize", layout);
    layout();

    // ---- Animation ---------------------------------------------------------
    function currentState() {
        for (const name of Object.keys(STATES)) {
            if (document.body.classList.contains(`state-${name}`)) {
                return STATES[name];
            }
        }
        return STATES.idle;
    }

    const clock = new THREE.Clock();
    let elapsed = 0;

    function animate() {
        requestAnimationFrame(animate);
        if (document.hidden || contextLost) {
            return;
        }

        const delta = Math.min(clock.getDelta(), 0.1);
        const target = currentState();
        const ease = 1 - Math.pow(0.02, delta);

        live.spin += (target.spin - live.spin) * ease;
        live.pulse += (target.pulse - live.pulse) * ease;
        live.wave += (target.wave - live.wave) * ease;
        live.glow += (target.glow - live.glow) * ease;
        live.color.lerp(targetColor.setHex(target.color), ease);

        elapsed += delta;
        const spin = delta * live.spin;
        const beat = 0.5 + 0.5 * Math.sin(elapsed * live.pulse * Math.PI);

        for (const material of tinted) {
            material.color.copy(live.color);
            material.opacity = Math.min(1, material.userData.baseOpacity * live.glow);
        }

        core.scale.setScalar(0.92 + beat * 0.16);
        coreGlow.scale.setScalar(2.6 + beat * 1.1);
        coreGlow.material.opacity = Math.min(1, (0.7 + beat * 0.3) * live.glow);

        innerRing.rotation.z -= spin * 1.2;
        segments.rotation.z += spin * 0.45;
        coil.rotation.z -= spin * 0.2;
        ticks.rotation.z += spin * 0.12;
        brackets.rotation.z -= spin * 0.08;
        for (const arc of arcs) {
            arc.rotation.z += spin * arc.userData.speed;
        }

        for (let i = 0; i < barCount; i++) {
            const angle = (i / barCount) * Math.PI * 2;
            const noise =
                (0.5 + 0.5 * Math.sin(elapsed * 6.0 + i * 0.7)) *
                (0.5 + 0.5 * Math.sin(elapsed * 3.3 + i * 1.9));
            const inner = 2.08;
            const outer = inner + 0.04 + live.wave * 0.32 * noise;
            const cos = Math.cos(angle);
            const sin = Math.sin(angle);
            barPositions.set([
                cos * inner, sin * inner, 0,
                cos * outer, sin * outer, 0
            ], i * 6);
        }
        barGeometry.attributes.position.needsUpdate = true;

        const pulsePhase = (elapsed * live.pulse * 0.35) % 1;
        pulseRing.scale.setScalar(0.6 + pulsePhase * (REACTOR_RADIUS + 0.4));
        pulseRing.material.opacity = (1 - pulsePhase) * 0.45 * live.glow;

        globe.rotation.y += spin * 0.06;

        for (const orbit of orbits) {
            orbit.angle += spin * orbit.speed;
            orbit.satellite.position.set(
                Math.cos(orbit.angle) * orbit.radius,
                Math.sin(orbit.angle) * orbit.radius,
                0
            );
        }

        grid.position.z = (elapsed * 1.5) % (120 / 80);

        for (let i = 0; i < dustCount; i++) {
            const index = i * 3 + 1;
            dustPositions[index] += dustSpeeds[i] * delta * (0.4 + live.spin * 0.25);
            if (dustPositions[index] > 35) {
                dustPositions[index] = -35;
            }
        }
        dustGeometry.attributes.position.needsUpdate = true;

        camera.position.set(
            Math.sin(elapsed * 0.15) * baseCameraZ * 0.05,
            Math.sin(elapsed * 0.11) * baseCameraZ * 0.025,
            baseCameraZ
        );
        camera.lookAt(0, 0, 0);

        renderer.render(scene, camera);
    }

    animate();
})();
