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
    renderTalkCourses();
    if (data.interesse_enviado) showTalkOk(null);
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

  // ---------------------------------------------------------------- quero conversar
  const talkForm = $("#talk-form");
  $("#btn-talk").addEventListener("click", () => {
    $("#btn-talk").classList.add("hidden");
    talkForm.classList.remove("hidden");
    track("clicou_conversar");
  });
  talkForm.addEventListener("change", (e) => {
    if (e.target.name === "quem") $("#resp-fields").classList.toggle("hidden", e.target.value !== "responsavel");
    $("#talk-error").textContent = "";
  });
  maskPhone(talkForm.elements.responsavel_telefone);

  function renderTalkCourses() {
    const box = $("#talk-cursos");
    const opts = [...data.cursos.map((c) => c.curso), "Ainda não sei"];
    if (!data.cursos.length || box.dataset.key === opts.join("|")) return;
    box.dataset.key = opts.join("|");
    box.innerHTML = opts.map((o) => `<label class="chip"><input type="radio" name="curso" value="${esc(o)}"><span>${esc(o)}</span></label>`).join("");
  }

  talkForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = talkForm.elements;
    const err = $("#talk-error");
    const curso = f.curso?.value, periodo = f.periodo.value, quem = f.quem.value;
    if (!curso) { err.textContent = "Escolha um curso (ou \"Ainda não sei\")."; return; }
    if (!periodo) { err.textContent = "Escolha o melhor período."; return; }
    if (quem === "responsavel" && phoneDigits(f.responsavel_telefone.value).length < 10) {
      err.textContent = "Informe o WhatsApp do responsável com DDD."; return;
    }
    const btn = $("#btn-talk-send");
    btn.disabled = true;
    try {
      const res = await fetch("/api/interesse", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token, curso, periodo, quem, dono, mensagem: f.mensagem.value,
          responsavel_nome: quem === "responsavel" ? f.responsavel_nome.value : "",
          responsavel_telefone: quem === "responsavel" ? f.responsavel_telefone.value : "",
        }),
      });
      const out = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(out.detail || "Não foi possível enviar. Tente de novo.");
      showTalkOk(out.whatsapp_link);
    } catch (ex) {
      err.textContent = ex.message;
    } finally {
      btn.disabled = false;
    }
  });

  function showTalkOk(waLink) {
    $("#btn-talk").classList.add("hidden");
    talkForm.classList.add("hidden");
    $("#talk-ok").classList.remove("hidden");
    if (waLink) { const a = $("#talk-wa"); a.href = waLink; a.classList.remove("hidden"); }
  }

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
