# Desktop Shell (Electron)

This folder is reserved for the Electron app shell.

Planned layout:
- main: Electron main process
- preload: secure bridge (IPC)
- renderer: reuse web UI from `apps/web`

Keep business logic in shared services so web and desktop can share code.