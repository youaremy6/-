/** 录音单例封装：全局只创建一次 RecorderManager（spec 7.1）。 */

const config = require('../config');

let manager = null;
let handlers = {};

function init() {
  if (manager) return manager;
  manager = wx.getRecorderManager();
  manager.onStart(function () {
    if (handlers.onStart) handlers.onStart();
  });
  manager.onStop(function (res) {
    if (handlers.onStop) handlers.onStop(res);
  });
  manager.onError(function (err) {
    if (handlers.onError) handlers.onError(err);
  });
  manager.onInterruptionBegin(function () {
    if (handlers.onInterruptionBegin) handlers.onInterruptionBegin();
  });
  manager.onInterruptionEnd(function () {
    if (handlers.onInterruptionEnd) handlers.onInterruptionEnd();
  });
  return manager;
}

function setHandlers(next) {
  handlers = next || {};
}

function start() {
  const instance = init();
  // spec 5.3: 16k / 单声道 / PCM / 30s / voiceRecognition
  instance.start({
    duration: config.MAX_RECORD_MS,
    sampleRate: 16000,
    numberOfChannels: 1,
    encodeBitRate: 24000,
    format: 'PCM',
    audioMode: 'voiceRecognition'
  });
}

function stop() {
  if (manager) {
    try {
      manager.stop();
    } catch (error) {
      console.warn('[recorder] stop failed', error);
    }
  }
}

module.exports = {
  init,
  setHandlers,
  start,
  stop
};
