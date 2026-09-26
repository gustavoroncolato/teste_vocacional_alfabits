(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const token = location.pathname.split("/").filter(Boolean).pop();
  const pageUrl = location.origin + "/r/" + token;
  let data = null;
  let active = 0;
  const rendered = [null, null, null]; // o que já foi desenhado em cada aba

  // quem está vendo é quem fez o teste? (família/amigos com o link contam separado)
  let dono = false;
  try { dono = JSON.parse(localStorage.getItem("tv_state_v2") || "{}")?.done?.token === token; } catch { /* sem storage */ }

  function track(tipo, extra = {}) {
    try {
      fetch("/api/evento", {
        method: "POST", keepalive: true, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, tipo, dono, ...extra }),
      }).catch(() => {});
    } catch { /* ignora */ }
  }

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const phoneDigits = (v) => v.replace(/\D/g, "").slice(0, 11);
  function maskPhone(input) {
    input.addEventListener("input", () => {
      const d = phoneDigits(input.value);
      let out = d;
      if (d.length > 2) out = `(${d.slice(0, 2)}) ${d.slice(2)}`;
      if (d.length > 7) out = `(${d.slice(0, 2)}) ${d.slice(2, d.length === 11 ? 7 : 6)}-${d.slice(d.length === 11 ? 7 : 6)}`;
      input.value = out;
    });
  }

  // ---------------------------------------------------------------- carregamento (a página se completa sozinha)
  let tries = 0;
  async function load() {
    try {
      const res = await fetch(`/api/resultado/${token}`, { cache: "no-store" });
      if (res.status === 404) { $("#r-hello").textContent = "Resultado não encontrado."; return; }
      data = await res.json();
      render();
      if (data.status !== "pronto" && tries++ < 150) setTimeout(load, tries < 20 ? 1500 : 3000);
    } catch {
      if (tries++ < 150) setTimeout(load, 3000);
    }
  }

  function render() {
    const [p1, p2] = data.perfil;
    const cap = (t) => t.charAt(0).toUpperCase() + t.slice(1);
    $("#r-hello").textContent = `${data.nome}, este é o seu resultado`;
    $("#r-title").innerHTML = `Seu perfil é <em>${esc(p1.nome)}</em> e <em>${esc(p2.nome)}</em>`;
    const traits = $("#r-traits");
    if (!traits.dataset.ok) {
      traits.dataset.ok = "1";
      traits.innerHTML = [p1, p2].map((p) => `<div class="trait"><b>${esc(p.nome)}</b><p>${esc(cap(p.descricao))}.</p></div>`).join("");
    }
    document.title = `Resultado de ${data.nome} | Teste Vocacional ${data.org.nome}`;
    renderTabs();
    data.cursos.forEach((c, i) => renderPanel(i, c));
    if (!data.cursos.length) renderWaiting();
    renderTalk();
  }

  function renderWaiting() {
    const panels = $("#panels");
    if (panels.dataset.waiting) return;
    panels.dataset.waiting = "1";
    panels.innerHTML = `<div class="panel active"><p class="writing">Escolhendo os cursos que mais combinam com você...</p>
      <div class="skel h"></div><div class="skel"></div><div class="skel w80"></div>
      <div class="skel h"></div><div class="skel"></div><div class="skel w60"></div></div>`;
  }

  function renderTabs() {
    const tabs = $("#tabs");
    const names = data.cursos.length ? data.cursos.map((c) => c.curso) : ["...", "...", "..."];
    const key = names.join("|") + active;
    if (tabs.dataset.key === key) return;
    tabs.dataset.key = key;
    tabs.innerHTML = names.map((n, i) => `
      <button class="tab" role="tab" aria-selected="${i === active}" data-i="${i}"><span class="n">0${i + 1}</span>${esc(n)}</button>`).join("");
    tabs.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => selectTab(+b.dataset.i)));
  }

  function selectTab(i) {
    if (!data.cursos[i] || i === active) return;
    active = i;
    renderTabs();
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", +p.dataset.i === i));
    const top = $("#tabs").getBoundingClientRect().top + window.scrollY;
    if (window.scrollY > top) window.scrollTo({ top, behavior: "smooth" });
    track("abriu_curso", { curso: data.cursos[i].curso });
  }

  function list(items, tag = "ul", cls = "") { return `<${tag} class="${cls}">${items.map((x) => `<li>${esc(x)}</li>`).join("")}</${tag}>`; }

  function renderPanel(i, c) {
    const d = c.detalhe;
    const state = d ? "full" : "partial";
    if (rendered[i] === state) return;
    rendered[i] = state;
    const panels = $("#panels");
    if (panels.dataset.waiting) { panels.innerHTML = ""; delete panels.dataset.waiting; }
    let el = panels.querySelector(`.panel[data-i="${i}"]`);
    if (!el) {
      el = document.createElement("section");
      el.className = "panel" + (i === active ? " active" : "");
      el.dataset.i = i;
      el.setAttribute("role", "tabpanel");
      panels.appendChild(el);
    }
    let html = `<h2 class="course-title">${esc(c.curso)}</h2>
      ${d && d.duracao ? `<p class="meta">Duração média: <b>${esc(d.duracao)}</b></p>` : ""}
      <div class="why"><span class="label">Por que combina com você</span><p>${esc(c.motivo)}</p></div>`;
    if (!d) {
      html += `<p class="writing">Preparando os detalhes deste curso...</p>
        <div class="skel h"></div><div class="skel"></div><div class="skel w80"></div>
        <div class="skel h"></div><div class="skel w60"></div><div class="skel w80"></div>`;
    } else {
      if (d.dia_a_dia) html += `<div class="block"><h3>Como é o dia a dia</h3><p>${esc(d.dia_a_dia)}</p></div>`;
      if (d.onde_trabalha?.length) html += `<div class="block"><h3>Onde dá para trabalhar</h3>${list(d.onde_trabalha, "ul", "tags")}</div>`;
      if (d.dicas?.length) html += `<div class="block"><h3>Para começar a se preparar</h3>${list(d.dicas, "ol", "steps-list")}</div>`;
      if (d.curiosidades?.length) html += `<div class="fact"><h3>Você sabia?</h3>${list(d.curiosidades)}</div>`;
    }
    el.innerHTML = html;
  }

  // ---------------------------------------------------------------- conversar com a Alfabits
  // Um toque: registra o interesse (lead quente no painel) e abre o WhatsApp da Alfabits com a mensagem pronta.
  function registerInterest() {
    track("clicou_conversar");
    try {
      fetch("/api/interesse", {
        method: "POST", keepalive: true, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, dono, quem: dono ? "aluno" : "responsavel" }),
      }).catch(() => {});
    } catch { /* ignora */ }
  }

  function renderTalk() {
    const wa = $("#btn-talk"), nowa = $("#btn-talk-nowa");
    if (data.whatsapp_link) {
      let link = data.whatsapp_link;
      if (!dono) {  // família/amigos vendo o resultado: mensagem em nome de quem está vendo
        const n = link.indexOf("?text=");
        const txt = `Olá! Vi o resultado do Teste Vocacional de ${data.nome}. Quero conhecer os cursos da ${data.org.nome}.`;
        link = link.slice(0, n) + "?text=" + encodeURIComponent(txt);
      }
      wa.href = link;
      wa.classList.remove("hidden");
    } else if (!data.interesse_enviado) {
      nowa.classList.remove("hidden");  // sem WhatsApp configurado: só registra e avisa
    } else {
      $("#talk-ok").classList.remove("hidden");
    }
  }
  $("#btn-talk").addEventListener("click", registerInterest);
  $("#btn-talk-nowa").addEventListener("click", () => {
    registerInterest();
    $("#btn-talk-nowa").classList.add("hidden");
    $("#talk-ok").classList.remove("hidden");
  });

  // ---------------------------------------------------------------- compartilhar / PDF
  const shareMsg = () => `Fiz o Teste Vocacional ${data?.org?.nome || "Alfabits"}! Veja meu resultado:`;
  const shareText = () => `${shareMsg()} ${pageUrl}`;
  // celular com HTTPS: abre a tela de compartilhar do próprio sistema (todos os apps).
  // sem suporte (computador ou http): mostra WhatsApp + copiar link.
  $("#btn-share").addEventListener("click", async () => {
    if (navigator.share) {
      track("compartilhou", { detalhe: "nativo" });
      try { await navigator.share({ title: "Meu Teste Vocacional", text: shareMsg(), url: pageUrl }); } catch { /* cancelado */ }
      return;
    }
    $("#share-wa").href = `https://wa.me/?text=${encodeURIComponent(shareText())}`;
    $("#share-menu").classList.toggle("hidden");
  });
  $("#share-wa").addEventListener("click", () => track("compartilhou", { detalhe: "whatsapp" }));
  $("#share-copy").addEventListener("click", async () => {
    track("compartilhou", { detalhe: "copiou_link" });
    try {
      await navigator.clipboard.writeText(pageUrl);
    } catch {  // navegadores sem clipboard (ex.: http)
      const t = document.createElement("textarea");
      t.value = pageUrl; document.body.appendChild(t); t.select();
      try { document.execCommand("copy"); } catch { /* ignora */ }
      t.remove();
    }
    const btn = $("#share-copy");
    btn.textContent = "Link copiado!";
    setTimeout(() => { btn.textContent = "Copiar link"; }, 2500);
  });
  const sharePhone = $("#share-phone");
  maskPhone(sharePhone);
  $("#btn-share-num").addEventListener("click", () => {
    const d = phoneDigits(sharePhone.value);
    if (d.length < 10) { $("#share-error").textContent = "Digite o número com DDD."; return; }
    $("#share-error").textContent = "";
    track("compartilhou_numero"); // o número digitado não é salvo
    window.open(`https://wa.me/55${d}?text=${encodeURIComponent(shareText())}`, "_blank", "noopener");
  });
  $("#btn-pdf").addEventListener("click", () => { track("salvou_pdf"); window.print(); });

  // ---------------------------------------------------------------- início
  try {
    if (!sessionStorage.getItem("viu_" + token)) { track("abriu_pagina"); sessionStorage.setItem("viu_" + token, "1"); }
  } catch { track("abriu_pagina"); }
  load();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
})();
