/* Casto 대시보드 서비스워커 — 껍데기는 캐시 우선, 데이터는 네트워크 우선.
   목적은 오프라인에서도 **캡처 번호표를 볼 수 있게** 하는 것이다(지하철에서 캡처 목록 확인). */
const SHELL = "casto-shell-v2";
const DATA = "casto-data-v2";
const FILES = ["./", "./index.html", "./manifest.json", "./icons/icon-192.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(
    ks.filter(k => k !== SHELL && k !== DATA).map(k => caches.delete(k))
  )).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.hostname === "raw.githubusercontent.com") {
    // 데이터: 네트워크 우선, 실패하면 마지막으로 성공한 응답을 준다
    e.respondWith(fetch(e.request).then(r => {
      const copy = r.clone();
      caches.open(DATA).then(c => c.put(e.request.url.split("?")[0], copy));
      return r;
    }).catch(() => caches.open(DATA).then(c => c.match(e.request.url.split("?")[0]))));
    return;
  }
  if (url.origin === location.origin) {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
  }
});
