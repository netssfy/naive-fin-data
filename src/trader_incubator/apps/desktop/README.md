# Desktop Shell (Electron)

这个目录是 Trader Incubator 的桌面壳工程，基于 Electron。

## 目录
- `main.js`：Electron 主进程，负责窗口创建与启动 Python API
- `preload.js`：预加载脚本（安全桥接）
- `package.json`：开发、构建、打包脚本与 electron-builder 配置

## 前置条件
- Windows
- Node.js 20+
- 项目根目录存在 Python 虚拟环境：`/.venv`（用于启动 `core/server.py`）

## 开发模式
在本目录执行：

```bash
npm install
npm run dev:all
```

含义：
- 启动 `apps/web` 的 Vite 前端（默认 `http://127.0.0.1:5173`）
- 等待前端可用后自动启动 Electron
- Electron 主进程会自动拉起 `src/trader_incubator/core/server.py`

## 构建桌面程序
在本目录执行：

```bash
npm install
npm run dist
```

产物输出到：
- `dist/win-unpacked/Trader Incubator.exe`

## 注意事项
- 桌面壳会把 `apps/web/dist`、`core` 打包到 Electron `resources`。
- 运行 Python API 的优先级：打包内 `python-venv`（如存在） > 系统 `python`。
