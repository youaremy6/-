const api = require('../../utils/api');
const audio = require('../../utils/audio');
const recorder = require('../../utils/recorder');
const settingsStore = require('../../utils/settings');
const stateModule = require('../../utils/state');
const format = require('../../utils/format');

const StateMachine = stateModule.StateMachine;

const SCENARIOS = [
  { id: 'medical', label: '就医' },
  { id: 'transport', label: '出行' },
  { id: 'market', label: '买卖' },
  { id: 'help', label: '日常' }
];

const PROVIDER_LABELS = {
  asr: '兰州话识别',
  llm: '语义转写',
  tts: '方言语音合成'
};

Page({
  data: {
    state: 'idle',
    direction: 'dialect',
    scenarios: SCENARIOS,
    scenario: '',
    statusText: '按住说兰州话',
    hintText: '',
    timerText: '00:00',
    result: null,
    error: null,
    editing: false,
    editText: '',
    textInput: '',
    showMicIntro: false,
    demoMode: false,
    demoText: '',
    serviceOffline: false,
    busy: false,
    playing: false
  },

  onLoad() {
    this.machine = new StateMachine((next) => this.onStateChange(next));
    this.settings = settingsStore.load();
    this.timer = null;
    this.progressTimers = [];
    this.recordStartedAt = 0;
    this.lastTempFile = '';
    this.lastDuration = 0;
    this.pendingRetry = null;
    this.discardNextStop = false;
    this.sessionToken = 0;

    this.setData({ scenario: this.settings.scenario || '' });
    recorder.setHandlers({
      onStop: (res) => this.handleRecorderStop(res),
      onError: () => this.handleRecorderError(),
      onInterruptionBegin: () => this.handleInterruption()
    });
    this.bindGlobalInterruption();
    this.loadHealth();
  },

  onShow() {
    this.settings = settingsStore.load();
    if (this.machine && this.machine.state !== 'idle') {
      this.machine.reset();
    }
    this.setData({
      busy: false,
      editing: false,
      playing: false
    });
  },

  onHide() {
    this.releaseAudioAndRecording(true);
  },

  onUnload() {
    this.releaseAudioAndRecording(false);
    audio.destroy();
    this.unbindGlobalInterruption();
  },

  // ---------------------------------------------------------------- health
  loadHealth() {
    api
      .health()
      .then((health) => {
        const deps = health.dependencies || {};
        const mocks = Object.keys(deps).filter((key) => deps[key].mode === 'mock');
        const names = mocks.map((key) => PROVIDER_LABELS[key]).filter(Boolean);
        const asrMock = deps.asr && deps.asr.mode === 'mock';
        this.setData({
          demoMode: names.length > 0,
          demoText: names.length
            ? names.join('、') +
              (asrMock
                ? ' 未接入：录音能上传，但不会识别你说的内容，返回的是内置预设句。'
                : ' 未接入：录音可本地识别，语义转写和方言语音合成仍为演示。')
            : '',
          serviceOffline: false
        });
      })
      .catch(() => {
        this.setData({
          serviceOffline: true,
          demoMode: false,
          hintText: '还没连上服务：请确认后端已启动；常用句仍可离线使用。'
        });
      });
  },

  // --------------------------------------------------------------- helpers
  onStateChange(next) {
    this.setData({
      state: next,
      statusText: this.statusFor(next, this.data.timerText),
      playing: next === 'playing'
    });
  },

  statusFor(state, timerText) {
    const isDialect = this.data.direction === 'dialect';
    const table = {
      idle: isDialect ? '按住说兰州话' : '输入普通话，生成兰州话',
      recording: '松开后翻译 · ' + (timerText || '00:00'),
      uploading: '正在上传…',
      recognizing: '正在听懂…',
      translating: isDialect ? '正在转成普通话…' : '正在生成兰州话…',
      synthesizing: '正在生成语音…',
      ready: isDialect ? '已转成普通话' : '已生成兰州话',
      playing: '正在播放',
      permission_required: '需要麦克风才能听你说话',
      permission_denied: '麦克风没打开，也可以先用常用句',
      too_short: '太短了，按住多说一会儿',
      too_long: '一次说一句，最多 30 秒',
      asr_empty: '没听清，再说一遍或直接改文字',
      low_confidence: '这句可能没听清，点文字改一下',
      network_error: '网络不稳，先看文字',
      tts_error: '方言语音暂时没生成，先用文字沟通',
      playback_error: '播放失败，检查音量或网络'
    };
    return table[state] || '按住说兰州话';
  },

  startTimer() {
    this.stopTimer();
    this.timer = setInterval(() => {
      const seconds = (Date.now() - this.recordStartedAt) / 1000;
      const text = format.formatSeconds(seconds);
      this.setData({
        timerText: text,
        statusText: this.statusFor('recording', text)
      });
    }, 250);
  },

  stopTimer() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  },

  startProgressTimer() {
    this.clearProgressTimer();
    this.progressTimers = [
      setTimeout(() => this.advanceTo('recognizing'), 500),
      setTimeout(() => this.advanceTo('translating'), 1600),
      setTimeout(() => this.advanceTo('synthesizing'), 3000)
    ];
  },

  clearProgressTimer() {
    (this.progressTimers || []).forEach((timer) => clearTimeout(timer));
    this.progressTimers = [];
  },

  advanceTo(next) {
    const current = this.machine.state;
    if (['uploading', 'recognizing', 'translating'].indexOf(current) < 0) return;
    this.machine.to(next);
  },

  releaseAudioAndRecording(resetState) {
    this.stopTimer();
    this.clearProgressTimer();
    this.sessionToken += 1;
    if (this.machine && this.machine.state === 'recording') {
      this.discardNextStop = true;
      recorder.stop();
    }
    audio.stop();
    if (resetState && this.machine) {
      this.machine.reset();
    }
    if (resetState) {
      this.setData({ busy: false, playing: false });
    }
  },

  clearError() {
    this.setData({ error: null, hintText: '' });
  },

  showError(code, options) {
    const defaults = {
      title: '这次没成功',
      message: '请重试，或改用常用句。',
      retryable: false,
      canEdit: false,
      showSettings: false
    };
    const error = Object.assign({ code }, defaults, options || {});
    this.setData({ error, hintText: '' });
    const next = stateModule.isError(code) ? code : 'network_error';
    this.machine.to(next);
  },

  // ------------------------------------------------------------- recording
  onPressStart() {
    if (this.data.busy || this.data.editing) return;
    if (this.machine.state === 'recording') return;
    if (!this.settings.micExplained) {
      this.setData({ showMicIntro: true });
      return;
    }
    this.checkPermissionAndRecord();
  },

  onPressEnd() {
    if (this.machine.state !== 'recording') return;
    this.stopTimer();
    const elapsed = Date.now() - this.recordStartedAt;
    if (elapsed < 800) {
      this.discardNextStop = true;
      recorder.stop();
      this.showError('too_short', {
        title: '说得太短',
        message: '太短了，按住多说一会儿。',
        retryable: false
      });
      return;
    }
    recorder.stop();
  },

  onConfirmMicIntro() {
    this.settings = settingsStore.save({ micExplained: true });
    this.setData({ showMicIntro: false });
    this.checkPermissionAndRecord();
  },

  onCancelMicIntro() {
    this.setData({ showMicIntro: false });
    wx.navigateTo({ url: '/pages/phrases/phrases' });
  },

  checkPermissionAndRecord() {
    const self = this;
    wx.getSetting({
      success(res) {
        const granted = res.authSetting && res.authSetting['scope.record'];
        if (granted === false) {
          self.onPermissionDenied();
          return;
        }
        if (granted === true) {
          self.beginRecording();
          return;
        }
        wx.authorize({
          scope: 'scope.record',
          success() {
            self.beginRecording();
          },
          fail() {
            self.onPermissionDenied();
          }
        });
      },
      fail() {
        self.beginRecording();
      }
    });
  },

  onPermissionDenied() {
    this.showError('permission_denied', {
      title: '需要麦克风',
      message: '需要麦克风才能听你说话；也可以在设置里打开权限，或先用常用句。',
      retryable: false,
      showSettings: true
    });
  },

  onOpenPermissionSettings() {
    const self = this;
    if (!wx.openSetting) return;
    wx.openSetting({
      success(res) {
        if (res.authSetting && res.authSetting['scope.record']) {
          self.clearError();
          self.machine.to('idle');
          self.beginRecording();
        }
      }
    });
  },

  beginRecording() {
    this.clearError();
    this.recordStartedAt = Date.now();
    this.setData({
      timerText: '00:00',
      result: null,
      editing: false,
      editText: '',
      hintText: ''
    });
    if (!this.machine.to('recording')) return;
    recorder.start();
    this.startTimer();
  },

  handleRecorderStop(res) {
    this.stopTimer();
    if (this.discardNextStop) {
      this.discardNextStop = false;
      return;
    }
    if (this.machine.state !== 'recording') return;

    const filePath = res && res.tempFilePath;
    const duration = (res && res.duration) || Date.now() - this.recordStartedAt;
    if (!filePath) {
      this.showError('recorder_error', {
        title: '录音没成功',
        message: '录音出错了，请重说一遍。'
      });
      return;
    }
    if (duration < 800) {
      this.showError('too_short', {
        title: '说得太短',
        message: '太短了，按住多说一会儿。'
      });
      return;
    }
    this.lastTempFile = filePath;
    this.lastDuration = duration;
    if (duration >= 29500) {
      this.setData({ hintText: '一次说一句，最多 30 秒；已经自动停止。' });
    }
    this.uploadRecording(filePath);
  },

  handleRecorderError() {
    this.stopTimer();
    this.showError('recorder_error', {
      title: '录音没成功',
      message: '录音出错了，请检查麦克风权限后重说。'
    });
  },

  handleInterruption() {
    if (this.machine.state === 'recording') {
      this.discardNextStop = true;
      recorder.stop();
      this.stopTimer();
      this.machine.to('idle');
      this.setData({
        result: null,
        hintText: '录音被打断了（可能有来电或微信语音），请重说一遍。'
      });
    }
    audio.stop();
    if (this.machine.state === 'playing') {
      this.machine.to('ready');
    }
  },

  bindGlobalInterruption() {
    this.onAudioInterruptionBegin = () => this.handleInterruption();
    this.onAudioInterruptionEnd = () => {
      if (this.machine.state === 'playing') this.machine.to('ready');
    };
    if (wx.onAudioInterruptionBegin) {
      wx.onAudioInterruptionBegin(this.onAudioInterruptionBegin);
    }
    if (wx.onAudioInterruptionEnd) {
      wx.onAudioInterruptionEnd(this.onAudioInterruptionEnd);
    }
  },

  unbindGlobalInterruption() {
    if (wx.offAudioInterruptionBegin && this.onAudioInterruptionBegin) {
      wx.offAudioInterruptionBegin(this.onAudioInterruptionBegin);
    }
    if (wx.offAudioInterruptionEnd && this.onAudioInterruptionEnd) {
      wx.offAudioInterruptionEnd(this.onAudioInterruptionEnd);
    }
  },

  // -------------------------------------------------------------- requests
  uploadRecording(filePath) {
    const token = this.sessionToken;
    const requestId = format.createRequestId();
    this.pendingRetry = { type: 'audio', filePath };
    this.setData({ busy: true, error: null, lastRequestId: requestId });
    settingsStore.setLastRequestId(requestId);
    if (!this.machine.to('uploading')) {
      this.setData({ busy: false });
      return;
    }
    this.startProgressTimer();
    api
      .translateAudio({
        requestId,
        filePath,
        scenario: this.data.scenario
      })
      .then(
        (res) => {
          this.clearProgressTimer();
          this.setData({ busy: false });
          if (token !== this.sessionToken) return;
          this.pendingRetry = null;
          this.applyDialectResult(res, requestId);
        },
        (err) => {
          this.clearProgressTimer();
          this.setData({ busy: false });
          if (token !== this.sessionToken) return;
          this.handleFailure(err, filePath);
        }
      );
  },

  applyDialectResult(res, requestId) {
    this.pendingRetry = null;
    const warnings = res.warnings || [];
    const result = {
      requestId,
      direction: 'dialect',
      inputTag: '对方 · 兰州话',
      inputText: res.asrText,
      outputTag: '我 · 普通话',
      outputText: res.outputText,
      backTranslation: '',
      audioUrl: res.outputAudioUrl || '',
      confidence: res.confidence,
      needsConfirmation: !!res.needsConfirmation,
      warnings,
      demo: warnings.indexOf('mock_asr') >= 0,
      ttsFailed: warnings.indexOf('tts_error') >= 0,
      playLabel: '播放普通话'
    };
    this.setData({
      result,
      editing: false,
      editText: '',
      error: null,
      hintText: '',
      timerText: '00:00'
    });
    this.machine.to('ready');
    this.maybeAutoplay(result);
  },

  applyReverseResult(res, requestId) {
    this.pendingRetry = null;
    const warnings = res.warnings || [];
    const result = {
      requestId,
      direction: 'mandarin',
      inputTag: '我 · 普通话',
      inputText: res.inputText,
      outputTag: '对方 · 兰州话',
      outputText: res.dialectText,
      backTranslation: res.backTranslation,
      audioUrl: res.outputAudioUrl || '',
      confidence: res.confidence,
      needsConfirmation: !!res.needsConfirmation,
      warnings,
      demo: false,
      ttsFailed: warnings.indexOf('tts_error') >= 0,
      playLabel: '播放兰州话'
    };
    this.setData({ result, editing: false, editText: '', error: null });
    this.machine.to('ready');
    this.maybeAutoplay(result);
  },

  handleFailure(err, filePath) {
    const code = (err && err.code) || 'network_error';
    const details = (err && err.details) || {};
    if (code === 'low_confidence') {
      this.setData({
        busy: false,
        editing: true,
        editText: details.asrText || '',
        error: {
          code,
          title: '这句可能没听清',
          message: '点文字改一下，或重说一遍。改完会重新翻译。',
          retryable: false,
          canEdit: true,
          showSettings: false
        }
      });
      this.machine.to('low_confidence');
      return;
    }

    const table = {
      too_short: { title: '说得太短', message: '太短了，按住多说一会儿。' },
      too_long: { title: '说得太长', message: '一次说一句，最多 30 秒。' },
      asr_empty: {
        title: '没听清',
        message: '没听清，再说一遍，或切到“说普通话”直接打字。',
        retryable: false
      },
      network_error: {
        title: '网络不稳',
        message: '网络不稳，先看文字；已保留这段录音，可以重试上传。',
        retryable: !!filePath
      },
      domain_blocked: {
        title: '请求域名未放行',
        message:
          '开发者工具请勾选“不校验合法域名、web-view、TLS 版本以及 HTTPS 证书”；真机需要把 https 域名加入 request 与 uploadFile 合法域名。',
        retryable: false
      },
      unsupported_audio: {
        title: '录音格式不支持',
        message: '这段录音无法识别，请重说一遍。'
      },
      empty_audio: { title: '没有录到声音', message: '没有录到声音，请重说。' },
      audio_too_large: { title: '录音太大', message: '这段录音太大，请分句说。' },
      asr_timeout: {
        title: '识别超时',
        message: '识别超时，已保留录音，可以重试上传。',
        retryable: !!filePath
      },
      llm_timeout: { title: '翻译超时', message: '翻译超时，请重试。', retryable: !!filePath },
      tts_timeout: { title: '语音合成超时', message: '语音合成超时，可以先用文字沟通。' },
      playback_error: {
        title: '播放失败',
        message: '播放失败，检查音量或网络后重试。'
      },
      permission_denied: {
        title: '需要麦克风',
        message: '需要麦克风才能听你说话，也可以先用常用句。',
        showSettings: true
      },
      recorder_error: { title: '录音没成功', message: '录音出错了，请重说一遍。' }
    };

    const mapped = table[code] || {
      title: '这次没成功',
      message: (err && err.message) || '服务暂时出错了，请重试或改用常用句。',
      retryable: !!(err && err.retryable) || !!filePath
    };
    if (filePath && mapped.retryable === undefined) {
      mapped.retryable = true;
    }
    // 文本/改字请求也能重试，但不能复用上一次的录音。
    const transient =
      code === 'network_error' ||
      code === 'llm_timeout' ||
      /(_timeout|_network_error|_upstream_error)$/.test(code) ||
      !!(err && err.retryable);
    if (this.pendingRetry && transient) {
      mapped.retryable = true;
      if (this.pendingRetry.type !== 'audio' && code === 'network_error') {
        mapped.message = '网络不稳，先看文字；可以重试这次翻译。';
      }
    }
    this.showError(code, mapped);
  },

  onRetry() {
    const retry = this.pendingRetry;
    if (!retry) {
      this.onDismissError();
      return;
    }
    this.clearError();
    this.machine.to('idle');
    if (retry.type === 'audio' && retry.filePath) {
      this.uploadRecording(retry.filePath);
      return;
    }
    if (retry.type === 'text') {
      this.onGenerateDialect();
      return;
    }
    if (retry.type === 'edit') {
      this.onConfirmEdit();
      return;
    }
    this.onDismissError();
  },

  onDismissError() {
    this.pendingRetry = null;
    this.clearError();
    this.machine.to('idle');
  },

  onUsePhrases() {
    wx.navigateTo({ url: '/pages/phrases/phrases' });
  },

  // --------------------------------------------------------------- reverse
  onTextInput(event) {
    this.setData({ textInput: event.detail.value });
  },

  onGenerateDialect() {
    if (this.data.busy) return;
    const text = (this.data.textInput || '').trim();
    if (!text) {
      this.setData({ hintText: '先写一句普通话，再生成兰州话。' });
      return;
    }
    const token = this.sessionToken;
    const requestId = format.createRequestId();
    this.pendingRetry = { type: 'text' };
    this.setData({ busy: true, error: null, hintText: '', result: null });
    this.machine.to('translating');
    api
      .translateText({ requestId, text, scenario: this.data.scenario })
      .then(
        (res) => {
          this.setData({ busy: false });
          if (token !== this.sessionToken) return;
          this.applyReverseResult(res, requestId);
        },
        (err) => {
          this.setData({ busy: false });
          if (token !== this.sessionToken) return;
          this.handleFailure(err, '');
        }
      );
  },

  // ------------------------------------------------------------------ edit
  onTapEdit() {
    const result = this.data.result;
    if (!result) return;
    if (!result.inputText) return;
    this.setData({ editing: true, editText: result.inputText, error: null });
  },

  onEditInput(event) {
    this.setData({ editText: event.detail.value });
  },

  onCancelEdit() {
    this.setData({ editing: false, editText: '', error: null });
    this.machine.to('ready');
  },

  onConfirmEdit() {
    const text = (this.data.editText || '').trim();
    if (!text) {
      this.setData({ hintText: '先把这句话写完整。' });
      return;
    }
    const result = this.data.result;
    if (!result || this.data.busy) return;
    const token = this.sessionToken;
    const requestId = format.createRequestId();
    this.pendingRetry = { type: 'edit' };
    this.setData({ busy: true, error: null, hintText: '' });
    this.machine.to('translating');

    const isDialect = result.direction === 'dialect';
    const promise = isDialect
      ? api.translateDialectText({ requestId, text, scenario: this.data.scenario })
      : api.translateText({ requestId, text, scenario: this.data.scenario });

    promise.then(
      (res) => {
        this.setData({ busy: false });
        if (token !== this.sessionToken) return;
        if (isDialect) {
          const warnings = res.warnings || [];
          const nextResult = {
            requestId,
            direction: 'dialect',
            inputTag: '对方 · 兰州话',
            inputText: text,
            outputTag: '我 · 普通话',
            outputText: res.outputText,
            backTranslation: '',
            audioUrl: res.outputAudioUrl || '',
            confidence: res.confidence,
            needsConfirmation: !!res.needsConfirmation,
            warnings,
            demo: false,
            ttsFailed: warnings.indexOf('tts_error') >= 0,
            playLabel: '播放普通话'
          };
          this.setData({
            result: nextResult,
            editing: false,
            editText: '',
            error: null
          });
          this.machine.to('ready');
          this.maybeAutoplay(nextResult);
        } else {
          this.applyReverseResult(res, requestId);
        }
      },
      (err) => {
        this.setData({ busy: false });
        if (token !== this.sessionToken) return;
        this.handleFailure(err, '');
      }
    );
  },

  // ------------------------------------------------------------- playback
  maybeAutoplay(result) {
    if (!this.settings.autoPlay) return;
    if (!result || !result.audioUrl) return;
    if (result.needsConfirmation) return;
    this.playResult();
  },

  onPlayResult() {
    const result = this.data.result;
    if (!result || !result.audioUrl) {
      this.setData({ hintText: '这段暂时没有语音，先用文字沟通。' });
      return;
    }
    this.playResult();
  },

  playResult() {
    const result = this.data.result;
    if (!result || !result.audioUrl) return;
    if (!this.machine.to('playing')) return;
    audio.play(result.audioUrl, {
      rate: this.settings.speechRate,
      onEnded: () => {
        if (this.machine.state === 'playing') this.machine.to('ready');
      },
      onError: () => {
        this.showError('playback_error', {
          title: '播放失败',
          message: '播放失败，检查音量或网络后可以重播。',
          retryable: false
        });
      }
    });
  },

  // ------------------------------------------------------------ navigation
  onSelectDirection(event) {
    if (this.data.busy || this.machine.state === 'recording') return;
    const direction = event.currentTarget.dataset.dir;
    if (!direction || direction === this.data.direction) return;
    audio.stop();
    this.pendingRetry = null;
    this.machine.to('idle');
    this.setData({
      direction,
      result: null,
      error: null,
      editing: false,
      editText: '',
      hintText: '',
      textInput: ''
    });
    // direction 已更新，重新计算 idle 文案（录音按钮文案随方向变化）。
    this.setData({ statusText: this.statusFor('idle') });
  },

  onSelectScenario(event) {
    const scenario = event.currentTarget.dataset.id || '';
    const next = scenario === this.data.scenario ? '' : scenario;
    this.settings = settingsStore.save({ scenario: next });
    this.setData({ scenario: next });
  },

  onResay() {
    this.pendingRetry = null;
    this.setData({
      result: null,
      error: null,
      editing: false,
      editText: '',
      hintText: ''
    });
    this.machine.to('idle');
  },

  onOpenPhrases() {
    wx.navigateTo({ url: '/pages/phrases/phrases' });
  },

  onOpenSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' });
  },

  noop() {}
});
