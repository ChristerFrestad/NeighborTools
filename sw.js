/* NeighborTools – app shell cache + Web Push */
const CACHE = 'nt-shell-v6';
const ASSETS = ['/', '/index.html', '/app.css', '/manifest.webmanifest'];

self.addEventListener('install', function(e){
  e.waitUntil(
    caches.open(CACHE).then(function(c){ return c.addAll(ASSETS); }).then(function(){
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function(e){
  e.waitUntil(
    caches.keys().then(function(keys){
      return Promise.all(keys.filter(function(k){ return k !== CACHE; }).map(function(k){
        return caches.delete(k);
      }));
    }).then(function(){ return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function(e){
  var url = new URL(e.request.url);
  // Never cache API – always network
  if(url.pathname.indexOf('/api/') === 0){
    return;
  }
  // App shell: network first, so a new version is picked up right away.
  // The cache is only a fallback for offline use.
  var isShell = e.request.mode === 'navigate' ||
                url.pathname === '/' || url.pathname === '/index.html';
  if(isShell){
    e.respondWith(
      fetch(e.request).then(function(res){
        var copy = res.clone();
        caches.open(CACHE).then(function(c){ c.put('/index.html', copy); });
        return res;
      }).catch(function(){
        return caches.match('/index.html');
      })
    );
    return;
  }
  e.respondWith(
    caches.match(e.request).then(function(cached){
      return cached || fetch(e.request).then(function(res){
        return res;
      }).catch(function(){
        return caches.match('/index.html');
      });
    })
  );
});

self.addEventListener('push', function(e){
  var data = {title: 'NeighborTools', body: '', url: '/'};
  try{
    if(e.data) data = Object.assign(data, e.data.json());
  }catch(err){
    try{ data.body = e.data ? e.data.text() : ''; }catch(e2){}
  }
  e.waitUntil(
    self.registration.showNotification(data.title || 'NeighborTools', {
      body: data.body || '',
      data: {url: data.url || '/'},
      tag: 'nt-' + (data.body || 'ping').slice(0, 40),
      renotify: true
    })
  );
});

self.addEventListener('notificationclick', function(e){
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(
    self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(function(list){
      for(var i = 0; i < list.length; i++){
        var c = list[i];
        if(c.url && c.url.indexOf(self.location.origin) === 0 && 'focus' in c){
          return c.focus();
        }
      }
      if(self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});
