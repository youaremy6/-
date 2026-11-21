const API_BASE = 'https://kentucky-wage-elections-organizing.trycloudflare.com';

module.exports = {
  // 临时演示地址；Cloudflare 隧道重启后会变化，正式部署请换成自己的 HTTPS 域名。
  // 开发者工具：勾选「不校验合法域名」；真机：把该 HTTPS 域名加入 request 合法域名。
  API_BASE,
  REQUEST_TIMEOUT: 20000,
  UPLOAD_TIMEOUT: 30000,
  MIN_RECORD_MS: 800,
  MAX_RECORD_MS: 30000
};
