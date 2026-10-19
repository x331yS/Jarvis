(() => {
    let bridge = null;
    let currentState = null;
    const context = new Map();

    const stateLabels = {
        idle: "STANDBY",
        listening: "LISTENING",
        thinking: "THINKING",
        executing: "EXECUTING",
        speaking: "SPEAKING",
        error: "ERROR"
    };

    const prompts = {
        idle: "Awaiting voice input",
        listening: "Listening...",
        thinking: "Processing request...",
        executing: "Executing command...",
        speaking: "Responding...",
        error: "System error"
    };

    function setState(state) {
        state = String(state || "idle").toLowerCase();
        if (state === currentState) {
            return;
        }
        if (currentState === null) {
            document.body.classList.add(`state-${state}`);
        } else {
            document.body.classList.replace(`state-${currentState}`, `state-${state}`);
        }
        currentState = state;

        const stateLabel = document.getElementById("stateLabel");
        const modeValue = document.getElementById("modeValue");
        const promptText = document.getElementById("promptText");

        if (stateLabel) {
            stateLabel.textContent =
                stateLabels[state] || state.toUpperCase();
        }

        if (modeValue) {
            modeValue.textContent = state.toUpperCase();
        }

        if (promptText) {
            promptText.textContent =
                prompts[state] || "System active";
        }

        if (window.jarvisPanels) {
            window.jarvisPanels.addActivity(
                prompts[state] || state
            );
        }
    }

    function setContext(key, value) {
        if (key !== "notification") {
            if (context.has(key) && context.get(key) === value) {
                return;
            }
            context.set(key, value);
        }
        if (key === "model") {
            const element = document.getElementById("modelValue");

            if (element) {
                element.textContent = value;
            }
        }

        if (window.jarvisPanels) {
            window.jarvisPanels.addActivity(`${key}: ${value}`);
        }
    }

    function updateClock() {
        const clock = document.getElementById("clock");

        if (!clock) {
            return;
        }

        clock.textContent = new Date().toLocaleTimeString(
            [],
            {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit"
            }
        );
    }

    window.jarvisHUD = {
        setState,
        setContext
    };

    function initBridge() {
        if (typeof QWebChannel === "undefined") {
            setState("error");
            return;
        }

        new QWebChannel(
            qt.webChannelTransport,
            function(channel) {
                bridge = channel.objects.jarvis;

                bridge.state_changed.connect(function(state) {
                    setState(state);
                });

                bridge.context_changed.connect(function(key, value) {
                    setContext(key, value);
                });

                bridge.snapshot(function(snapshot) {
                    setState(snapshot.state);
                    for (const [key, value] of Object.entries(snapshot.context)) {
                        setContext(key, value);
                    }
                });
            }
        );
    }

    setInterval(updateClock, 1000);

    updateClock();
    initBridge();
})();