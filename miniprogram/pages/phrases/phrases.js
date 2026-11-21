const audio = require('../../utils/audio');
const settingsStore = require('../../utils/settings');
const pack = require('../../data/phrases.js');

const SCENARIOS = [
  { id: '', label: '全部' },
  { id: 'medical', label: '就医' },
  { id: 'transport', label: '出行' },
  { id: 'market', label: '买卖' },
  { id: 'help', label: '日常' }
];

const SCENARIO_LABEL = {
  medical: '就医',
  transport: '出行',
  market: '买卖',
  help: '日常'
};

function localPath(meta) {
  if (!meta || !meta.file) return '';
  return '/assets/phrases/' + meta.file;
}

Page({
  data: {
    scenarios: SCENARIOS,
    active: '',
    items: [],
    count: 0,
    draftCount: 0,
    notice: pack.notice || '',
    reviewPolicy: pack.reviewPolicy || '',
    fullscreen: null,
    playingKey: ''
  },

  onLoad() {
    this.settings = settingsStore.load();
    this.build('');
  },

  onShow() {
    this.settings = settingsStore.load();
  },

  onUnload() {
    audio.stop();
  },

  build(scenario) {
    const self = this;
    const items = (pack.phrases || [])
      .filter(function (phrase) {
        return !scenario || phrase.scenario === scenario;
      })
      .map(function (phrase) {
        return {
          id: phrase.id,
          scenario: phrase.scenario,
          scenarioLabel: SCENARIO_LABEL[phrase.scenario] || '场景',
          mandarin: phrase.mandarin,
          lanzhou: phrase.lanzhou,
          reviewStatus: phrase.reviewStatus,
          isDraft: phrase.reviewStatus !== 'verified',
          note: phrase.note || '',
          mandarinLocal: localPath(phrase.mandarinAudio),
          lanzhouLocal: localPath(phrase.lanzhouAudio),
          mandarinKind: phrase.mandarinAudio ? phrase.mandarinAudio.kind : 'missing',
          lanzhouKind: phrase.lanzhouAudio ? phrase.lanzhouAudio.kind : 'missing',
          lanzhouPlaceholder: !!(phrase.lanzhouAudio && phrase.lanzhouAudio.kind === 'placeholder')
        };
      });
    const drafts = items.filter(function (item) {
      return item.isDraft;
    }).length;
    self.setData({ items, active: scenario, count: items.length, draftCount: drafts });
  },

  onSelectTab(event) {
    const id = event.currentTarget.dataset.id || '';
    this.build(id);
  },

  findItem(id) {
    return this.data.items.find(function (item) {
      return item.id === id;
    });
  },

  playItem(item, language) {
    if (!item) return;
    const src = language === 'mandarin' ? item.mandarinLocal : item.lanzhouLocal;
    if (!src) {
      wx.showToast({ title: '这条还没有音频', icon: 'none' });
      return;
    }
    const key = item.id + ':' + language;
    const self = this;
    audio.play(src, {
      rate: this.settings.speechRate,
      onEnded() {
        self.setData({ playingKey: '' });
      },
      onError() {
        self.setData({ playingKey: '' });
        wx.showToast({ title: '播放失败，检查音量', icon: 'none' });
      }
    });
    this.setData({ playingKey: key });
  },

  onPlayCard(event) {
    const id = event.currentTarget.dataset.id;
    const language = event.currentTarget.dataset.lang || 'lanzhou';
    this.playItem(this.findItem(id), language);
  },

  onOpenFull(event) {
    const id = event.currentTarget.dataset.id;
    const item = this.findItem(id);
    if (!item) return;
    this.setData({ fullscreen: item });
  },

  onCloseFull() {
    audio.stop();
    this.setData({ fullscreen: null, playingKey: '' });
  },

  onPlayFull(event) {
    const language = event.currentTarget.dataset.lang || 'lanzhou';
    const item = this.data.fullscreen;
    this.playItem(item, language);
  },

  noop() {}
});
