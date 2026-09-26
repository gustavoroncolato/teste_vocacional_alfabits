(() => {
  "use strict";
  const KEY = "tv_state_v2";
  const TOTAL = 12 + 12 + 1;
  const $ = (s) => document.querySelector(s);

  let state = load() || fresh();
  let busy = false;

  function fresh() {
    return { screen: "intro", id: null, escala: [], fase1: [], fase2: [], abertasQs: [], answers: {}, phase: 1, idx: 0, abertas: {}, done: null, perfil: null };
  }
  function load() { try { return JSON.parse(localStorage.getItem(KEY)); } catch { return null; } }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* sem storage: segue em memória */ } }

  function show(name) {
    document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("active", s.id === "s-" + name));
    if (name !== "loading") { state.screen = name; save(); }
    window.scrollTo(0, 0);
  }

  function toast(msg) {
    const t = document.createElement("div");
    t.className = "toast"; t.textContent = msg; t.setAttribute("role", "alert");
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 4500);
  }

  async function api(path, body) {
    let res;
    try {
      res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } catch {
      throw new Error("Sem conexão. Verifique a internet e tente de novo.");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.detail || "Algo deu errado. Tente novamente.");
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function sessionLost(err) {
    if (err.status === 404) {
      toast("Sua sessão expirou. Vamos recomeçar.");
      const perfil = state.perfil; state = fresh(); state.perfil = perfil; save();
      fillForm(); show("form");
      return true;
    }
    return false;
  }

  // ---------------------------------------------------------------- intro
  document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => { fillForm(); show(b.dataset.go); }));
  const resumeBtn = $("#btn-resume");
  if (state.done && state.done.url) {
    resumeBtn.textContent = "Ver meu resultado";
    resumeBtn.classList.remove("hidden");
  } else if (state.id && state.screen !== "intro") {
    resumeBtn.classList.remove("hidden");
  }
  resumeBtn.addEventListener("click", () => {
    if (state.done && state.done.url) { location.href = state.done.url; return; }
    if (state.screen === "open") return renderOpen();
    if (state.screen === "quiz") return renderQuestion();
    show("form");
  });

  // ---------------------------------------------------------------- formulário
  const form = $("#profile-form");
  const phone = form.elements.telefone;
  phone.addEventListener("input", () => {
    const d = phone.value.replace(/\D/g, "").slice(0, 11);
    let out = d;
    if (d.length > 2) out = `(${d.slice(0, 2)}) ${d.slice(2)}`;
    if (d.length > 7) out = `(${d.slice(0, 2)}) ${d.slice(2, d.length === 11 ? 7 : 6)}-${d.slice(d.length === 11 ? 7 : 6)}`;
    phone.value = out;
  });
  form.elements.nascimento.max = new Date().toISOString().slice(0, 10);
  form.addEventListener("change", () => { $("#form-error").textContent = ""; });

  function fillForm() {
    const p = state.perfil; if (!p) return;
    for (const [k, v] of Object.entries(p)) {
      const el = form.elements[k]; if (!el) continue;
      if (el.type === "checkbox") el.checked = !!v; else el.value = v || "";
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    const f = form.elements;
    const perfil = {
      nome: f.nome.value.trim(), telefone: f.telefone.value, nascimento: f.nascimento.value,
      cidade: f.cidade.value.trim(), escola: f.escola.value.trim(), serie: f.serie.value || null,
      aceita_lgpd: f.aceita_lgpd.checked, aceita_contato: f.aceita_contato.checked,
    };
    const err = $("#form-error");
    const missing = [["nome", "seu nome"], ["telefone", "seu WhatsApp"], ["nascimento", "sua data de nascimento"], ["cidade", "sua cidade"], ["escola", "onde você estuda"]]
      .find(([k]) => !perfil[k]);
    if (missing) { err.textContent = `Preencha ${missing[1]}.`; f[missing[0]].focus(); return; }
    if (perfil.telefone.replace(/\D/g, "").length < 10) { err.textContent = "Informe o WhatsApp com DDD."; f.telefone.focus(); return; }
    if (!perfil.aceita_lgpd) { err.textContent = "Marque a autorização (LGPD) para continuar."; return; }
    err.textContent = "";
    busy = true; $("#btn-start").disabled = true;
    try {
      const data = await api("/api/iniciar", perfil);
      state = { ...fresh(), perfil, id: data.id, escala: data.escala, fase1: data.perguntas };
      renderQuestion();
    } catch (ex) {
      err.textContent = ex.message;
    } finally {
      busy = false; $("#btn-start").disabled = false;
    }
  });

  // ---------------------------------------------------------------- perguntas
  function currentList() { return state.phase === 1 ? state.fase1 : state.fase2; }
  function progress(el, done) { $(el).style.width = Math.round((done / TOTAL) * 100) + "%"; }

  function renderQuestion() {
    const list = currentList();
    const q = list[state.idx];
    const n = (state.phase === 1 ? 0 : 12) + state.idx;
    progress("#bar", n);
    $("#qcount").textContent = `Pergunta ${n + 1} de 24`;
    $("#qphase").textContent = state.phase === 1 ? "Parte 1 de 2" : "Parte 2 de 2";
    $("#qtext").textContent = q.texto;
    const box = $("#options");
    box.innerHTML = "";
    state.escala.forEach((opt) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "option" + (state.answers[q.id] === opt.value ? " selected" : "");
      b.innerHTML = `<span class="dot"></span><span></span>`;
      b.lastChild.textContent = opt.label;
      b.addEventListener("click", () => answer(q.id, opt.value, b));
      box.appendChild(b);
    });
    show("quiz");
  }

  async function answer(qid, value, btn) {
    if (busy) return;
    busy = true;
    state.answers[qid] = value;
    document.querySelectorAll(".option").forEach((o) => o.classList.remove("selected"));
    btn.classList.add("selected");
    save();
    await new Promise((r) => setTimeout(r, 180));
    try {
      if (state.idx < currentList().length - 1) {
        state.idx++; renderQuestion();
      } else if (state.phase === 1) {
        await loadPhase2();
      } else {
        renderOpen();
      }
    } finally {
      busy = false;
    }
  }

  async function loadPhase2() {
    $("#loading-text").textContent = "Preparando perguntas feitas para o seu perfil...";
    $("#loading-sub").textContent = "Isso leva só alguns segundos.";
    $("#loading-steps").classList.add("hidden");
    show("loading");
    const respostas = {};
    state.fase1.forEach((q) => { respostas[q.id] = state.answers[q.id]; });
    try {
      const data = await api("/api/fase2", { id: state.id, respostas });
      state.fase2 = data.perguntas; state.abertasQs = data.abertas;
      // se a pessoa voltou e mudou respostas, descarta respostas antigas da fase 2
      const ids = new Set(state.fase2.map((q) => q.id));
      Object.keys(state.answers).forEach((k) => { if (k.startsWith("p2_") && !ids.has(k)) delete state.answers[k]; });
      state.phase = 2; state.idx = 0;
      renderQuestion();
    } catch (ex) {
      if (sessionLost(ex)) return;
      toast(ex.message);
      state.idx = state.fase1.length - 1; renderQuestion();
    }
  }

  $("#btn-back").addEventListener("click", () => {
    if (busy) return;
    if (state.idx > 0) { state.idx--; return renderQuestion(); }
    if (state.phase === 2) { state.phase = 1; state.idx = state.fase1.length - 1; return renderQuestion(); }
    fillForm(); show("form");
  });

  // ---------------------------------------------------------------- abertas
  const MIN_PADRAO = 15;
  const minOf = (q) => q.min || MIN_PADRAO;
  const letras = (v) => new Set(v.toLowerCase().replace(/[^a-zà-ú]/g, "")).size;
  const abertaOk = (q) => { const v = (state.abertas[q.id] || "").trim(); return v.length >= minOf(q) && letras(v) >= 5; };

  function renderOpen() {
    progress("#bar2", 24);
    $("#open-error").textContent = "";
    const f = $("#open-form");
    f.innerHTML = "";
    state.abertasQs.forEach((q) => {
      const l = document.createElement("label");
      l.textContent = q.texto;
      const t = document.createElement("textarea");
      t.name = q.id; t.maxLength = 400; t.placeholder = q.placeholder || "";
      t.value = state.abertas[q.id] || "";
      const c = document.createElement("span");
      c.className = "counter";
      const upd = () => {
        const n = t.value.trim().length, ok = abertaOk(q);
        c.textContent = ok ? "Ótimo!" : `${n} de ${minOf(q)} caracteres no mínimo`;
        c.classList.toggle("ok", ok);
        if (ok) t.classList.remove("invalid");
      };
      t.addEventListener("input", () => { state.abertas[q.id] = t.value; save(); upd(); });
      upd();
      l.appendChild(t); l.appendChild(c); f.appendChild(l);
    });
    show("open");
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // etapas na tela de carregamento: ficam pelo menos 3 a 5 s (dá tempo de a IA escolher os cursos)
  async function stagedLoading(work) {
    const items = [...document.querySelectorAll("#loading-steps li")];
    $("#loading-text").textContent = "Preparando seu resultado";
    $("#loading-sub").textContent = "Só um instante, estamos olhando com calma para as suas respostas.";
    $("#loading-steps").classList.remove("hidden");
    items.forEach((li) => li.classList.remove("now", "done"));
    show("loading");
    const minimo = 3000 + Math.random() * 2000;
    const passo = minimo / items.length;
    let stop = false;
    const anim = (async () => {
      for (let i = 0; i < items.length; i++) {
        items[i].classList.add("now");
        await sleep(passo);
        if (i < items.length - 1 || stop) { items[i].classList.remove("now"); items[i].classList.add("done"); }
      }
    })();
    try {
      return await work();
    } finally {
      await anim;
      stop = true;
      items.forEach((li) => { li.classList.remove("now"); li.classList.add("done"); });
      await sleep(250);
    }
  }

  // espera a IA escolher os 3 cursos (até ~8 s a mais), para a página já abrir com as abas
  async function waitCourses(token) {
    const fim = Date.now() + 8000;
    while (Date.now() < fim) {
      try {
        const r = await fetch(`/api/resultado/${token}`, { cache: "no-store" });
        if (r.ok && (await r.json()).cursos.length) return;
      } catch { /* segue */ }
      await sleep(1000);
    }
  }

  $("#btn-finish").addEventListener("click", async () => {
    if (busy) return;
    const falta = state.abertasQs.find((q) => !abertaOk(q));
    if (falta) {
      const t = $(`#open-form textarea[name="${falta.id}"]`);
      $("#open-error").textContent = `Escreva um pouco mais (mínimo de ${minOf(falta)} caracteres). Quanto mais você contar, melhor fica o resultado.`;
      if (t) { t.classList.add("invalid"); t.focus(); }
      return;
    }
    busy = true;
    const respostas = {};
    state.fase2.forEach((q) => { respostas[q.id] = state.answers[q.id]; });
    try {
      await stagedLoading(async () => {
        state.done = await api("/api/finalizar", { id: state.id, respostas, abertas: state.abertas });
        save();
        await waitCourses(state.done.token);
      });
      location.href = state.done.url;
    } catch (ex) {
      $("#loading-steps").classList.add("hidden");
      if (!sessionLost(ex)) { show("open"); $("#open-error").textContent = ex.message; }
    } finally {
      busy = false;
    }
  });

  // ---------------------------------------------------------------- PWA
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
  }
})();
