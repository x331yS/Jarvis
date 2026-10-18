(() => {
    function addActivity(message) {
        const activity = document.getElementById("activity");

        if (!activity) {
            return;
        }

        const row = document.createElement("div");
        row.className = "activity-line";

        const time = document.createElement("span");
        time.className = "activity-time";

        const now = new Date();

        time.textContent = now.toLocaleTimeString(
            [],
            {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit"
            }
        );

        const text = document.createElement("span");
        text.textContent = message;

        row.appendChild(time);
        row.appendChild(text);

        activity.prepend(row);

        while (activity.children.length > 5) {
            activity.removeChild(activity.lastChild);
        }
    }

    window.jarvisPanels = {
        addActivity
    };
})();