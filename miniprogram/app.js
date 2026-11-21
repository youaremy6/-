const config = require('./config');
const settingsStore = require('./utils/settings');

App({
  globalData: {
    apiBase: config.API_BASE,
    settings: null,
    health: null
  },

  onLaunch() {
    this.globalData.settings = settingsStore.load();
  },

  onShow() {
    this.globalData.settings = settingsStore.load();
  }
});
