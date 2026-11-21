/** 播放单例：页面卸载时 destroy，避免音频实例泄漏（spec 7.1）。 */

let context = null;
let endedHandler = null;
let errorHandler = null;

function ensure() {
  if (context) return context;
  context = wx.createInnerAudioContext();
  context.obeyMuteSwitch = false;
  context.onEnded(function () {
    if (endedHandler) endedHandler();
  });
  context.onError(function (err) {
    if (errorHandler) errorHandler(err);
  });
  return context;
}

function play(src, options) {
  if (!src) return;
  const opts = options || {};
  const instance = ensure();
  try {
    instance.stop();
  } catch (error) {
    // 未开始播放时 stop 可能抛错，忽略。
  }
  endedHandler = opts.onEnded || null;
  errorHandler = opts.onError || null;
  try {
    if (opts.rate) instance.playbackRate = opts.rate;
  } catch (error) {
    // 部分基础库不支持 playbackRate，按原速播放。
  }
  instance.src = src;
  instance.play();
}

function stop() {
  if (!context) return;
  try {
    context.stop();
  } catch (error) {
    // ignore
  }
}

function destroy() {
  if (!context) return;
  try {
    context.stop();
    context.destroy();
  } catch (error) {
    // ignore
  }
  context = null;
  endedHandler = null;
  errorHandler = null;
}

module.exports = {
  play,
  stop,
  destroy
};
