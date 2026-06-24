// Service worker do painel da Malu — recebe os pushes de lead novo (Fase 3).

// Handler de fetch (pass-through pra rede). Não cacheia nada — só existe pra o
// navegador considerar o app instalável (critério de PWA do Chrome/Android).
// No iOS o "Adicionar à Tela de Início" já funciona só com o manifest.
self.addEventListener("fetch", () => {
  // network pass-through — sem interceptar
});

self.addEventListener("push", (event) => {
  let data = { title: "Malu", body: "Novo lead", url: "/" };
  try {
    if (event.data) data = Object.assign(data, event.data.json());
  } catch (e) {
    // payload não-JSON: mantém o default
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      data: { url: data.url },
      tag: "malu-lead",
      renotify: true,
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((wins) => {
        for (const w of wins) {
          if ("focus" in w) {
            w.navigate(url);
            return w.focus();
          }
        }
        if (self.clients.openWindow) return self.clients.openWindow(url);
      }),
  );
});
