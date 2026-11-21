/**
 * 明确的状态机（spec 4.3）。所有页面状态切换都走这里，避免出现 undefined 状态
 * 或“转圈停不下来”。
 */

const STATES = [
  'idle',
  'permission_required',
  'recording',
  'uploading',
  'recognizing',
  'translating',
  'synthesizing',
  'ready',
  'playing'
];

const ERROR_STATES = [
  'permission_denied',
  'too_short',
  'too_long',
  'asr_empty',
  'low_confidence',
  'network_error',
  'tts_error',
  'playback_error'
];

const TRANSITIONS = {
  idle: ['permission_required', 'recording', 'translating', 'playing'],
  permission_required: ['permission_denied', 'recording', 'idle'],
  recording: ['uploading', 'too_short', 'too_long', 'idle'],
  uploading: ['recognizing', 'translating', 'synthesizing', 'ready', 'network_error', 'idle'],
  recognizing: ['translating', 'synthesizing', 'ready', 'asr_empty', 'low_confidence', 'network_error', 'idle'],
  translating: ['synthesizing', 'ready', 'tts_error', 'network_error', 'idle'],
  synthesizing: ['ready', 'tts_error', 'idle'],
  ready: ['playing', 'recording', 'translating', 'idle'],
  playing: ['ready', 'idle', 'playback_error'],
  permission_denied: ['idle', 'recording', 'ready'],
  too_short: ['idle', 'recording', 'translating', 'ready'],
  too_long: ['idle', 'recording', 'translating', 'ready'],
  asr_empty: ['idle', 'recording', 'translating', 'ready'],
  low_confidence: ['idle', 'recording', 'translating', 'ready'],
  network_error: ['idle', 'recording', 'translating', 'uploading', 'ready'],
  tts_error: ['idle', 'recording', 'translating', 'ready'],
  playback_error: ['idle', 'ready']
};

function isError(state) {
  return ERROR_STATES.indexOf(state) >= 0;
}

function isKnown(state) {
  return STATES.indexOf(state) >= 0 || ERROR_STATES.indexOf(state) >= 0;
}

class StateMachine {
  constructor(onChange) {
    this.state = 'idle';
    this.previous = null;
    this.onChange = typeof onChange === 'function' ? onChange : function () {};
  }

  can(next) {
    if (next === this.state) return true;
    if (!isKnown(next)) return false;
    // 清理永远允许；进入错误状态永远允许，避免卡死。
    if (next === 'idle') return true;
    if (isError(next) && !isError(this.state)) return true;
    const allowed = TRANSITIONS[this.state] || [];
    return allowed.indexOf(next) >= 0;
  }

  to(next) {
    if (!this.can(next)) {
      console.warn('[state] illegal transition', this.state, '->', next);
      return false;
    }
    const previous = this.state;
    this.state = next;
    this.previous = previous;
    this.onChange(next, previous);
    return true;
  }

  reset() {
    if (this.state !== 'idle') {
      const previous = this.state;
      this.state = 'idle';
      this.previous = previous;
      this.onChange('idle', previous);
    }
  }

  isError() {
    return isError(this.state);
  }
}

module.exports = {
  STATES,
  ERROR_STATES,
  TRANSITIONS,
  StateMachine,
  isError,
  isKnown
};
