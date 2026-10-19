# Local Windows audio

`systemAudio` controls Windows Core Audio locally, without administrator rights,
external services or shell commands.

- `list` returns raw JSON containing active playback endpoint names/IDs and the default output.
- `set_output` resolves an exact name/ID or a unique case-insensitive partial name, ignoring spacing and punctuation. Missing and ambiguous devices fail explicitly with available names.
- A selected output becomes the console, multimedia and communications default.
- Switching output preserves every device's volume and mute state. Model numbers are not volume requests.
- `set_volume` accepts either an absolute percentage `volume` (0 to 100), or relative percentage-point `change` (-100 to 100), never both. Relative changes clamp at 0 and 100. The target is the current default unless a device is named.
- Invalid inputs do not mutate audio settings. API/dependency failures return explicit errors and diagnostic logs.
- Results contain device data and observed volume, not generated prose.
- Each invocation initialises and releases COM on its calling thread.
- The tool is discoverable through the standard builtin registry, planner and router.
- The tool description includes action values and argument semantics so text-tool mode carries the same contract as native JSON schemas.
- Piper resolves the fresh Windows default playback endpoint for each utterance through MME or DirectSound, without reinitialising PortAudio or interrupting microphone capture.
- Other platforms return an explicit unsupported-platform error.

Tests cover discovery, listing, switching without volume changes, absolute/relative volume,
clamping, invalid/ambiguous requests and API errors. Local LLM evaluations cover French
device/volume commands and French-only replies.
