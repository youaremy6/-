/**
 * Headless simulation of the mini program pages against the real backend.
 *
 * WeChat devtools is not available in this environment, so this script stubs
 * the `wx` APIs (storage, request, uploadFile, recorder, audio, modal) and
 * drives the real page code: onLoad/onShow, hold-to-talk -> upload -> result,
 * edit/correct, reverse text flow, phrases page, settings + delete record.
 *
 * Usage:
 *   python -m uvicorn app.main:app --app-dir server --port 8000
 *   node scripts/simulate_miniprogram.mjs
 *
 * Exit codes: 0 ok, 1 assertion failed, 2 backend not reachable.
 */

import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const MP = join(ROOT, 'miniprogram');
const require = createRequire(import.meta.url);
const API = process.env.XG_API_BASE || 'http://127.0.0.1:8000';

const storage = new Map();
const navigations = [];
const toasts = [];
let audioPlays = 0;
let audioContext = null;
let recorderManager = null;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(predicate, label, timeout = 12000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (predicate()) return;
    await sleep(50);
  }
  throw new Error(`timeout waiting for ${label}`);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function createAudioContext() {
  const context = {
    src: '',
    playbackRate: 1,
    obeyMuteSwitch: false,
    _ended: null,
    _error: null,
    onEnded(handler) {
      this._ended = handler;
    },
    onError(handler) {
      this._error = handler;
    },
    play() {
      audioPlays += 1;
      setTimeout(() => {
        if (this._ended) this._ended();
      }, 5);
    },
    stop() {},
    destroy() {}
  };
  return context;
}

function createRecorderManager() {
  let startedAt = 0;
  const handlers = {};
  return {
    onStart(handler) {
      handlers.start = handler;
    },
    onStop(handler) {
      handlers.stop = handler;
    },
    onError(handler) {
      handlers.error = handler;
    },
    onInterruptionBegin(handler) {
      handlers.interruption = handler;
    },
    onInterruptionEnd(handler) {
      handlers.interruptionEnd = handler;
    },
    start() {
      startedAt = Date.now();
      setTimeout(() => handlers.start && handlers.start(), 0);
    },
    stop() {
      const duration = Math.max(900, Date.now() - startedAt);
      setTimeout(() => handlers.stop && handlers.stop({ tempFilePath: '/tmp/fake.pcm', duration }), 0);
    }
  };
}

function pcmBytes(seconds = 1.2) {
  return Buffer.alloc(16_000 * 2 * seconds, 0x10);
}

global.wx = {
  getStorageSync(key) {
    return storage.has(key) ? storage.get(key) : '';
  },
  setStorageSync(key, value) {
    storage.set(key, value);
  },
  removeStorageSync(key) {
    storage.delete(key);
  },
  getSetting({ success }) {
    success({ authSetting: { 'scope.record': true } });
  },
  authorize({ success }) {
    success({});
  },
  openSetting({ success }) {
    success({ authSetting: { 'scope.record': true } });
  },
  createInnerAudioContext() {
    if (!audioContext) audioContext = createAudioContext();
    return audioContext;
  },
  getRecorderManager() {
    if (!recorderManager) recorderManager = createRecorderManager();
    return recorderManager;
  },
  request({ url, method = 'GET', data, success, fail }) {
    const options = { method, headers: { 'content-type': 'application/json' } };
    if (data !== undefined) options.body = JSON.stringify(data);
    fetch(url, options)
      .then(async (response) => {
        const text = await response.text();
        success({ statusCode: response.status, data: text });
      })
      .catch((error) => fail && fail(error));
  },
  uploadFile({ url, name, filePath, formData, success, fail }) {
    const form = new FormData();
    Object.keys(formData || {}).forEach((key) => form.append(key, formData[key]));
    form.append(name, new Blob([pcmBytes()], { type: 'application/octet-stream' }), 'speech.pcm');
    fetch(url, { method: 'POST', body: form })
      .then(async (response) => {
        const text = await response.text();
        success({ statusCode: response.status, data: text });
      })
      .catch((error) => fail && fail(error));
  },
  navigateTo({ url }) {
    navigations.push(url);
  },
  showToast(options) {
    toasts.push(options && options.title);
  },
  showModal({ success }) {
    success({ confirm: true });
  },
  onAudioInterruptionBegin() {},
  onAudioInterruptionEnd() {},
  offAudioInterruptionBegin() {},
  offAudioInterruptionEnd() {}
};

function loadPage(relative) {
  let definition = null;
  global.Page = (config) => {
    definition = config;
  };
  const file = join(MP, relative + '.js');
  delete require.cache[require.resolve(file)];
  require(file);
  assert(definition, `Page() not called by ${relative}`);

  const instance = Object.assign({}, definition);
  instance.data = JSON.parse(JSON.stringify(definition.data || {}));
  instance.setData = function setData(patch, callback) {
    Object.assign(this.data, patch);
    if (callback) callback();
  };
  return instance;
}

async function checkBackend() {
  const response = await fetch(`${API}/api/v1/health`);
  if (!response.ok) throw new Error(`health ${response.status}`);
  const body = await response.json();
  return body;
}

async function run() {
  const health = await checkBackend();
  console.log(`backend: ${health.status} phrases=${health.limits.phraseCount}`);

  global.wx.setStorageSync('xg_settings', {
    speechRate: 1.0,
    autoPlay: true,
    micExplained: true,
    scenario: ''
  });

  // ---------------------------------------------------------------- index
  const index = loadPage('pages/index/index');
  index.onLoad();
  index.onShow();
  await waitFor(() => index.data.demoMode === true, 'health banner');
  assert(index.data.state === 'idle', 'initial state must be idle');
  assert(index.data.statusText === '按住说兰州话', `idle label was ${index.data.statusText}`);

  index.onSelectScenario({ currentTarget: { dataset: { id: 'medical' } } });
  assert(index.data.scenario === 'medical', 'scenario selection');

  index.onPressStart();
  assert(index.data.state === 'recording', `state after press was ${index.data.state}`);
  await sleep(1000);
  assert(/松开后翻译/.test(index.data.statusText), 'recording status copy');

  index.onPressEnd();
  await waitFor(() => index.data.result, 'dialect result');
  const first = index.data.result;
  assert(first.inputText && first.outputText, 'result texts');
  assert(first.audioUrl, 'result audio url');
  assert(first.demo === true, 'mock asr flagged as demo');
  assert(index.data.state === 'ready' || index.data.state === 'playing', `state ${index.data.state}`);
  console.log(`dialect: ${first.inputText} -> ${first.outputText}`);

  // edit the transcript and re-translate through /translate/dialect-text
  index.onTapEdit();
  assert(index.data.editing === true, 'edit mode');
  index.onEditInput({ detail: { value: '大夫，我脑壳有点晕。' } });
  index.onConfirmEdit();
  await waitFor(() => index.data.result && index.data.result.inputText === '大夫，我脑壳有点晕。', 'edited result');
  await waitFor(() => index.data.busy === false, 'edit busy false');
  assert(index.data.result.outputText === '医生，我有点头晕。', `edited output ${index.data.result.outputText}`);
  console.log(`edited: ${index.data.result.inputText} -> ${index.data.result.outputText}`);

  index.onPlayResult();
  await sleep(50);
  assert(index.data.state === 'ready', 'playback finished to ready');

  // reverse direction
  index.onSelectDirection({ currentTarget: { dataset: { dir: 'mandarin' } } });
  assert(index.data.direction === 'mandarin', 'direction switch');
  index.onTextInput({ detail: { value: '医生，我有点头晕。' } });
  index.onGenerateDialect();
  await waitFor(() => index.data.result && index.data.result.direction === 'mandarin', 'reverse result');
  await waitFor(() => index.data.busy === false, 'reverse busy false');
  const reverse = index.data.result;
  assert(reverse.outputText === '大夫，我脑壳有点晕。', `reverse output ${reverse.outputText}`);
  assert(reverse.backTranslation, 'back translation present');
  assert(reverse.audioUrl, 'reverse audio url');
  console.log(`reverse: ${reverse.inputText} -> ${reverse.outputText}`);

  // one-shot network failure on the reverse request, then retry must re-generate
  // (not re-upload a stale recording from the earlier hold-to-talk).
  index.onResay();
  const originalRequest = global.wx.request;
  let failedOnce = false;
  global.wx.request = function (options) {
    if (!failedOnce && String(options.url).indexOf('/translate/text') >= 0) {
      failedOnce = true;
      if (options.fail) options.fail(new Error('simulated network down'));
      return;
    }
    originalRequest(options);
  };
  index.onTextInput({ detail: { value: '这个多少钱一斤？' } });
  index.onGenerateDialect();
  await waitFor(() => index.data.error, 'reverse network error');
  assert(failedOnce, 'network failure was injected');
  assert(index.data.error.retryable === true, 'network error must be retryable');
  assert(index.pendingRetry && index.pendingRetry.type === 'text', 'retry intent must be text');
  index.onRetry();
  await waitFor(() => index.data.result && index.data.result.outputText === '这个多少钱一斤？', 'retry result');
  global.wx.request = originalRequest;
  console.log('reverse retry: ok');

  // -------------------------------------------------------------- phrases
  const phrases = loadPage('pages/phrases/phrases');
  phrases.onLoad();
  phrases.onShow();
  assert(phrases.data.items.length === 27, `phrase count ${phrases.data.items.length}`);
  phrases.onSelectTab({ currentTarget: { dataset: { id: 'medical' } } });
  assert(phrases.data.items.length === 7, `medical count ${phrases.data.items.length}`);
  phrases.onSelectTab({ currentTarget: { dataset: { id: 'help' } } });
  assert(phrases.data.items.length === 7, `help count ${phrases.data.items.length}`);
  phrases.onSelectTab({ currentTarget: { dataset: { id: '' } } });
  phrases.onPlayCard({ currentTarget: { dataset: { id: 'medical_01', lang: 'lanzhou' } } });
  assert(audioPlays > 0, 'phrase playback invoked');
  phrases.onOpenFull({ currentTarget: { dataset: { id: 'medical_01' } } });
  assert(phrases.data.fullscreen && phrases.data.fullscreen.id === 'medical_01', 'fullscreen phrase');
  phrases.onPlayFull({ currentTarget: { dataset: { lang: 'mandarin' } } });
  phrases.onCloseFull();
  assert(phrases.data.fullscreen === null, 'fullscreen closed');

  // ------------------------------------------------------------- settings
  const settings = loadPage('pages/settings/settings');
  settings.onShow();
  assert(settings.data.lastRequestId, 'last request id stored');
  settings.onRateChange({ currentTarget: { dataset: { value: 1.2 } } });
  assert(settings.data.rate === 1.2, 'rate saved');
  settings.onAutoPlayChange({ detail: { value: false } });
  assert(settings.data.autoPlay === false, 'autoplay saved');
  settings.onDeleteRecord();
  await waitFor(() => settings.data.lastRequestId === '', 'record deleted');
  console.log('settings: rate/autoplay/delete ok');

  const deletedResponse = await fetch(`${API}/api/v1/records/${first.requestId}`, { method: 'DELETE' });
  assert(deletedResponse.status === 404, 'record must be gone after delete');
  console.log(`audio_plays=${audioPlays} navigations=${navigations.length} toasts=${toasts.length}`);
  console.log('MINIPROGRAM SIMULATION OK');
}

run().catch((error) => {
  if (error && error.cause && error.cause.code === 'ECONNREFUSED') {
    console.error('backend not reachable; start uvicorn first');
    process.exit(2);
  }
  console.error('SIMULATION FAILED:', error && error.message ? error.message : error);
  process.exit(1);
});
