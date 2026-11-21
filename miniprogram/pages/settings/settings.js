const api = require('../../utils/api');
const config = require('../../config');
const settingsStore = require('../../utils/settings');

Page({
  data: {
    rateOptions: [
      { value: 0.8, label: '慢 0.8' },
      { value: 1.0, label: '正常 1.0' },
      { value: 1.2, label: '快 1.2' }
    ],
    rate: 1.0,
    autoPlay: true,
    lastRequestId: '',
    deleting: false,
    version: '0.1.0',
    apiBase: config.API_BASE
  },

  onShow() {
    const settings = settingsStore.load();
    this.setData({
      rate: settings.speechRate,
      autoPlay: settings.autoPlay,
      lastRequestId: settingsStore.lastRequestId()
    });
  },

  onRateChange(event) {
    const value = Number(event.currentTarget.dataset.value);
    if ([0.8, 1.0, 1.2].indexOf(value) < 0) return;
    settingsStore.save({ speechRate: value });
    this.setData({ rate: value });
  },

  onAutoPlayChange(event) {
    const value = !!event.detail.value;
    settingsStore.save({ autoPlay: value });
    this.setData({ autoPlay: value });
  },

  onResetMicIntro() {
    settingsStore.save({ micExplained: false });
    wx.showToast({ title: '下次按住说话会重新提示', icon: 'none' });
  },

  onDeleteRecord() {
    const requestId = this.data.lastRequestId;
    if (!requestId) {
      wx.showToast({ title: '还没有可删除的记录', icon: 'none' });
      return;
    }
    const self = this;
    wx.showModal({
      title: '删除本次记录',
      content: '会删除这次生成并缓存的语音；原话和译文本来就不保存。',
      confirmText: '删除',
      confirmColor: '#A84F32',
      success(result) {
        if (!result.confirm) return;
        self.setData({ deleting: true });
        api.deleteRecord(requestId).then(
          function () {
            settingsStore.setLastRequestId('');
            self.setData({ deleting: false, lastRequestId: '' });
            wx.showToast({ title: '已删除', icon: 'success' });
          },
          function (err) {
            self.setData({ deleting: false });
            if (err && err.code === 'record_not_found') {
              settingsStore.setLastRequestId('');
              self.setData({ lastRequestId: '' });
              wx.showToast({ title: '记录已过期，本地已清理', icon: 'none' });
              return;
            }
            wx.showToast({ title: (err && err.message) || '删除失败，请重试', icon: 'none' });
          }
        );
      }
    });
  },

  onOpenPhrases() {
    wx.navigateTo({ url: '/pages/phrases/phrases' });
  },

  onTestBackend() {
    const self = this;
    wx.showLoading({ title: '测试后端…' });
    api.health().then(
      function (health) {
        wx.hideLoading();
        const deps = health.dependencies || {};
        const mocks = Object.keys(deps).filter(function (key) {
          return deps[key].mode === 'mock';
        });
        wx.showModal({
          title: '后端可用',
          content:
            '状态：' +
            health.status +
            '\n地址：' +
            self.data.apiBase +
            '\n演示依赖：' +
            (mocks.length ? mocks.join('、') : '无'),
          showCancel: false
        });
      },
      function (err) {
        wx.hideLoading();
        wx.showModal({
          title: '后端连不上',
          content:
            (err && err.message ? err.message : '请求失败') +
            '\n地址：' +
            self.data.apiBase +
            '\n开发者工具请勾选“不校验合法域名”；真机请把该 HTTPS 域名加入 request 合法域名。',
          showCancel: false
        });
      }
    );
  }
});
