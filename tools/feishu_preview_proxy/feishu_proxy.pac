function FindProxyForURL(url, host) {
  var proxied = {
    "internal-api-drive-stream.feishu.cn": true,
    "internal-api-lark-api.feishu.cn": true,
    "weboffice.feishu-3rd-party-services.com": true
  };
  if (proxied[host]) {
    return "PROXY 127.0.0.1:18080";
  }
  return "DIRECT";
}
