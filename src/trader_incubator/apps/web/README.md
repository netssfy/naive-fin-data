# Web Frontend

React + TypeScript + Vite starter prepared for future Electron migration.

## Stack

- React 19 + TypeScript
- Vite 8
- React Router
- Zustand
- Tailwind CSS v4

## Run

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
npm run preview
```

## Structure

- `src/app`: app bootstrap and router
- `src/components`: reusable UI layout
- `src/pages`: route pages
- `src/store`: app state
- `../desktop`: Electron shell placeholder

## Electron-ready principles

- Keep business code platform-agnostic.
- Use adapters for file-system and native APIs.
- Inject desktop capabilities through preload + IPC.