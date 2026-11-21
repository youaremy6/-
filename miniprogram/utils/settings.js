/** 本地设置：语速、自动播放、首次麦克风说明、场景记忆。 */

const KEY = 'xg_settings';
const LAST_RECORD = 'xg_last_record';

const DEFAULTS = {
  speechRate: 1.0,
  autoPlay: true,
  micExplained: false,
  scenario: ''
};

function load() {
  let saved = {};
  try {
    saved = wx.getStorageSync(KEY) || {};
  } catch (error) {
    saved = {};
  }
  const merged = {};
  Object.keys(DEFAULTS).forEach(function (key) {
    merged[key] = saved[key] === undefined || saved[key] === null ? DEFAULTS[key] : saved[key];
  });
  if ([0.8, 1.0, 1.2].indexOf(merged.speechRate) < 0) {
    merged.speechRate = DEFAULTS.speechRate;
  }
  return merged;
}

function save(patch) {
  const next = load();
  Object.keys(patch || {}).forEach(function (key) {
    next[key] = patch[key];
  });
  try {
    wx.setStorageSync(KEY, next);
  } catch (error) {
    console.warn('[settings] save failed', error);
  }
  return next;
}

function lastRequestId() {
  try {
    return wx.getStorageSync(LAST_RECORD) || '';
  } catch (error) {
    return '';
  }
}

function setLastRequestId(requestId) {
  try {
    if (requestId) {
      wx.setStorageSync(LAST_RECORD, requestId);
    } else {
      wx.removeStorageSync(LAST_RECORD);
    }
  } catch (error) {
    console.warn('[settings] last record save failed', error);
  }
}

module.exports = {
  DEFAULTS,
  load,
  save,
  lastRequestId,
  setLastRequestId
};
