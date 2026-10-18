# System Applications Tool Specification

`systemApps` opens or closes a supported desktop application on the local
Windows computer. It operates on local processes and application launch
protocols; it does not search the web or call an application service.

## Interface

The tool accepts an `action` (`open` or `close`) and an `app` from its
declared schema. Application names are case-insensitive and accept the aliases
implemented by the tool.

Supported applications are Spotify, Brave, Chrome, Firefox, VS Code, Notepad
and File Explorer.

## Behaviour

- `open` starts the selected installed application and reports a clear error
  when its executable cannot be resolved or started.
- Spotify is opened using the local `spotify:` Windows protocol handler.
- File Explorer opens with `explorer.exe`; closing it is intentionally
  unsupported.
- `close` terminates the supported application's named process. An
  unavailable or unsupported process returns an error instead of reporting
  success.
- Invalid actions and malformed arguments return an unsuccessful tool result.
