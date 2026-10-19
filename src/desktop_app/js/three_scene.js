(() => {
    const canvas = document.getElementById("space");
    const ctx = canvas.getContext("2d");

    let width = 0;
    let height = 0;

    const particles = [];

    function resize() {
        width = canvas.width = window.innerWidth * devicePixelRatio;
        height = canvas.height = window.innerHeight * devicePixelRatio;

        canvas.style.width = `${window.innerWidth}px`;
        canvas.style.height = `${window.innerHeight}px`;

        ctx.setTransform(
            devicePixelRatio,
            0,
            0,
            devicePixelRatio,
            0,
            0
        );

        particles.length = 0;

        const count = Math.min(
            220,
            Math.floor(window.innerWidth * window.innerHeight / 9000)
        );

        for (let i = 0; i < count; i++) {
            particles.push({
                x: Math.random() * window.innerWidth,
                y: Math.random() * window.innerHeight,
                z: Math.random(),
                speed: 0.1 + Math.random() * 0.45,
                size: 0.5 + Math.random() * 1.5
            });
        }
    }

    function draw() {
        ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

        for (const particle of particles) {
            particle.y -= particle.speed;

            if (particle.y < 0) {
                particle.y = window.innerHeight;
                particle.x = Math.random() * window.innerWidth;
            }

            const alpha = 0.15 + particle.z * 0.6;

            ctx.beginPath();
            ctx.fillStyle = `rgba(98,230,255,${alpha})`;
            ctx.arc(
                particle.x,
                particle.y,
                particle.size * particle.z,
                0,
                Math.PI * 2
            );
            ctx.fill();
        }

        requestAnimationFrame(draw);
    }

    window.addEventListener("resize", resize);

    resize();
    draw();
})();