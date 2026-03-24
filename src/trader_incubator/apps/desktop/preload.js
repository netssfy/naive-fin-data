const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('desktop', {
  apiBaseUrl: `http://${process.env.ELECTRON_API_HOST || '127.0.0.1'}:${process.env.ELECTRON_API_PORT || '8000'}`,
});
