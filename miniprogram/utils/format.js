/** 小工具：时间显示与请求 ID。 */

function pad2(value) {
  return value < 10 ? '0' + value : String(value);
}

function formatSeconds(seconds) {
  const safe = Math.max(0, Math.floor(seconds || 0));
  return pad2(Math.floor(safe / 60)) + ':' + pad2(safe % 60);
}

function createRequestId() {
  const stamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 8);
  return 'req_' + stamp + random;
}

module.exports = {
  pad2,
  formatSeconds,
  createRequestId
};
