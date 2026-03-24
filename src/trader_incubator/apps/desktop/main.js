const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const isDev = !app.isPackaged;
const rendererDevUrl = process.env.ELECTRON_RENDERER_URL || 'http://127.0.0.1:5173';

let backendProcess = null;

function findRepoPythonBin() {
  const root = path.resolve(__dirname, '../../../../');
  return path.join(root, '.venv', 'Scripts', 'python.exe');
}

function startBackend() {
  const script = app.isPackaged
    ? path.join(process.resourcesPath, 'core', 'server.py')
    : path.resolve(__dirname, '../../core/server.py');

  const cwd = path.dirname(script);
  const env = {
    ...process.env,
    PYTHONIOENCODING: 'utf-8',
  };
  const candidates = app.isPackaged
    ? [path.join(process.resourcesPath, 'python-venv', 'Scripts', 'python.exe'), 'python']
    : [findRepoPythonBin(), 'python'];

  for (const python of candidates) {
    if (python.endsWith('.exe') && !fs.existsSync(python)) {
      continue;
    }

    backendProcess = spawn(python, [script], {
      cwd,
      env,
      stdio: 'ignore',
      windowsHide: true,
    });

    backendProcess.on('exit', () => {
      backendProcess = null;
    });

    backendProcess.on('error', () => {
      backendProcess = null;
    });

    break;
  }
}

function stopBackend() {
  if (!backendProcess) {
    return;
  }
  backendProcess.kill();
  backendProcess = null;
}

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1400,
    height: 920,
    minWidth: 1100,
    minHeight: 700,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (isDev) {
    mainWindow.loadURL(rendererDevUrl);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
    return;
  }

  const indexPath = path.join(process.resourcesPath, 'web-dist', 'index.html');
  mainWindow.loadFile(indexPath);
}

app.whenReady().then(() => {
  startBackend();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  stopBackend();
});