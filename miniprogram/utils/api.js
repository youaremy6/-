/** 请求封装：统一错误结构，避免页面里到处判断 statusCode。 */

const config = require('../config');

function buildError(statusCode, body, fallbackMessage) {
  if (body && body.error && body.error.code) {
    return {
      code: body.error.code,
      message: body.error.message || fallbackMessage,
      retryable: !!body.error.retryable,
      details: body.error.details || {},
      statusCode: statusCode
    };
  }
  return {
    code: 'http_error',
    message: fallbackMessage || '服务暂时出错了，请重试。',
    retryable: statusCode >= 500,
    details: {},
    statusCode: statusCode
  };
}

function parseBody(data) {
  if (typeof data !== 'string') return data;
  try {
    return JSON.parse(data);
  } catch (error) {
    return null;
  }
}

function failError(err, fallbackMessage) {
  const message = String((err && (err.errMsg || err.message)) || '');
  // 微信最常见的两种“后端连不上”：域名白名单 / 未勾选不校验合法域名。
  if (/domain|合法域名|not in domain|url not in/i.test(message)) {
    return {
      code: 'domain_blocked',
      message:
        '请求域名未放行：开发者工具请勾选“不校验合法域名、web-view、TLS 版本以及 HTTPS 证书”；真机需要把 https 域名加入 request 与 uploadFile 合法域名。',
      retryable: false,
      details: {},
      raw: err
    };
  }
  return {
    code: 'network_error',
    message: fallbackMessage || '网络不稳，先看文字或改用常用句。',
    retryable: true,
    details: {},
    raw: err
  };
}

function request(path, options) {
  const opts = options || {};
  return new Promise(function (resolve, reject) {
    wx.request({
      url: config.API_BASE + path,
      method: opts.method || 'GET',
      data: opts.data,
      timeout: config.REQUEST_TIMEOUT,
      header: opts.header || { 'content-type': 'application/json' },
      success: function (res) {
        const body = parseBody(res.data);
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(body);
          return;
        }
        reject(buildError(res.statusCode, body, '请求没有成功，请重试。'));
      },
      fail: function (err) {
        reject(failError(err, '网络不稳，先看文字或改用常用句。'));
      }
    });
  });
}

function translateAudio(params) {
  return new Promise(function (resolve, reject) {
    wx.uploadFile({
      url: config.API_BASE + '/api/v1/translate/audio',
      filePath: params.filePath,
      name: 'audio',
      timeout: config.UPLOAD_TIMEOUT,
      formData: {
        requestId: params.requestId,
        dialectId: 'lanzhou',
        scenario: params.scenario || ''
      },
      success: function (res) {
        const body = parseBody(res.data);
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(body);
          return;
        }
        reject(buildError(res.statusCode, body, '识别没有成功，请重试。'));
      },
      fail: function (err) {
        reject(failError(err, '网络不稳，已保留这段录音，可以重试上传。'));
      }
    });
  });
}

function translateText(params) {
  return request('/api/v1/translate/text', {
    method: 'POST',
    data: {
      requestId: params.requestId,
      direction: 'mandarin_to_dialect',
      dialectId: 'lanzhou',
      scenario: params.scenario || null,
      text: params.text
    }
  });
}

function translateDialectText(params) {
  return request('/api/v1/translate/dialect-text', {
    method: 'POST',
    data: {
      requestId: params.requestId,
      dialectId: 'lanzhou',
      scenario: params.scenario || null,
      text: params.text
    }
  });
}

function fetchPhrases(scenario) {
  const suffix = scenario ? '?scenario=' + encodeURIComponent(scenario) : '';
  return request('/api/v1/phrases' + suffix);
}

function health() {
  return request('/api/v1/health');
}

function deleteRecord(requestId) {
  return request('/api/v1/records/' + encodeURIComponent(requestId), { method: 'DELETE' });
}

module.exports = {
  request,
  translateAudio,
  translateText,
  translateDialectText,
  fetchPhrases,
  health,
  deleteRecord,
  buildError
};
