(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let all = [];
  let stats = {};

  // ---------------------------------------------------------------- formatação
  function fmtPhone(t) {
    const d = String(t || "").replace(/\D/g, "").replace(/^55/, "");
    if (d.length < 10) return t || "";
    return `(${d.slice(0, 2)}) ${d.slice(2, d.length - 4)}-${d.slice(-4)}`;
  }
  const waLink = (t) => `https://wa.me/${String(t || "").replace(/\D/g, "")}`;
  function fmtDate(iso, withTime = true) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString("pt-BR", withTime ? { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }
      : { day: "2-digit", month: "2-digit", year: "numeric" });
  }
  const fmtBirth = (s) => (s ? s.split("-").reverse().join("/") : "");
  const TEMP = { quente: "Quente", morno: "Morno", frio: "Frio" };
  const tempBadge = (t) => (t ? `<span class="temp ${t}">${TEMP[t]}</span>` : `<span class="temp pend">Não terminou</span>`);
  const yesNo = (v, yes = "Sim", no = "Não") => (v ? `<span class="yes">${yes}</span>` : `<span class="no">${no}</span>`);
  const STATUS = { respondendo: "Parou no meio do teste", na_fila: "Gerando resultado", detalhando: "Gerando resultado", pronto: "Resultado pronto" };
  const COMO = { nativo: "tela de compartilhar do celular", whatsapp: "WhatsApp", copiou_link: "copiou o link", numero: "enviou para um número" };

  // ---------------------------------------------------------------- login
  let timer = null;
  function lockCountdown(seg) {
    const btn = $("#btn-login");
    clearInterval(timer);
    const end = Date.now() + seg * 1000;
    const tick = () => {
      const left = Math.max(0, Math.ceil((end - Date.now()) / 1000));
      if (!left) { clearInterval(timer); btn.disabled = false; btn.textContent = "Entrar"; return; }
      btn.disabled = true;
      const h = Math.floor(left / 3600), m = Math.floor((left % 3600) / 60), s = left % 60;
      btn.textContent = `Aguarde ${h ? h + "h " : ""}${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    };
    tick();
    timer = setInterval(tick, 1000);
  }

  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target.elements;
    const err = $("#login-error");
    if (!f.usuario.value.trim() || !f.senha.value) { err.textContent = "Preencha usuário e senha."; return; }
    err.textContent = "";
    $("#btn-login").disabled = true;
    try {
      const res = await fetch("/api/admin/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ usuario: f.usuario.value, senha: f.senha.value }),
      });
      const out = await res.json().catch(() => ({}));
      if (!res.ok) {
        err.textContent = out.detail || "Não foi possível entrar.";
        f.senha.value = "";
        if (out.espera) lockCountdown(out.espera); else $("#btn-login").disabled = false;
        return;
      }
      f.senha.value = "";
      $("#btn-login").disabled = false;
      await load();
    } catch {
      err.textContent = "Sem conexão com o servidor.";
      $("#btn-login").disabled = false;
    }
  });

  function showLogin() {
    $("#dash").classList.add("hidden");
    $("#login").classList.remove("hidden");
    $("#login-form").elements.usuario.focus();
  }

  $("#btn-logout").addEventListener("click", async () => {
    await fetch("/api/admin/logout", { method: "POST" }).catch(() => {});
    all = [];
    showLogin();
  });

  // ---------------------------------------------------------------- dados
  async function load() {
    const btn = $("#btn-refresh");
    btn.disabled = true;
    try {
      const res = await fetch("/api/admin/participantes", { cache: "no-store" });
      if (res.status === 401) { showLogin(); return; }
      const out = await res.json();
      all = out.participantes; stats = out.stats;
      $("#login").classList.add("hidden");
      $("#dash").classList.remove("hidden");
      fillFilters();
      renderStats();
      render();
    } catch {
      alert("Não foi possível carregar os dados.");
    } finally {
      btn.disabled = false;
    }
  }
  $("#btn-refresh").addEventListener("click", load);

  function renderStats() {
    const done = all.filter((p) => p.temperatura);
    const n = (fn) => all.filter(fn).length;
    const cards = [
      [all.length, "Começaram o teste"],
      [n((p) => p.status === "pronto"), "Com resultado pronto"],
      [n((p) => p.interesse), "Pediram para conversar", true],
      [n((p) => p.aceita_contato), "Autorizaram contato"],
      [done.filter((p) => p.temperatura === "quente").length, "Leads quentes"],
      [done.filter((p) => p.temperatura === "morno").length, "Leads mornos"],
      [done.filter((p) => p.temperatura === "frio").length, "Leads frios"],
      [n((p) => p.compartilhou), "Compartilharam"],
      [n((p) => p.views_outros), "Família/amigos abriram"],
      [n((p) => p.pdf), "Salvaram em PDF"],
      [n((p) => p.status === "respondendo"), "Pararam no meio"],
    ];
    if (stats.na_fila_agora) cards.push([stats.na_fila_agora, "Na fila da IA agora"]);
    $("#stats").innerHTML = cards.map(([v, l, hl]) => `<div class="stat${hl ? " hl" : ""}"><b>${v}</b><span>${l}</span></div>`).join("");
  }

  // ---------------------------------------------------------------- filtros
  const F = ["busca", "cidade", "escola", "idade", "serie", "contato", "temp", "conversar", "compart", "ordem"];
  const el = (k) => $("#f-" + k);
  function options(sel, values, label) {
    const cur = sel.value;
    sel.innerHTML = `<option value="">${label}</option>` + values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("");
    if (values.map(String).includes(cur)) sel.value = cur;
  }
  const uniq = (arr) => [...new Set(arr.filter((x) => x !== "" && x !== null && x !== undefined))];
  function fillFilters() {
    const byName = (a, b) => String(a).localeCompare(String(b), "pt-BR");
    options(el("cidade"), uniq(all.map((p) => p.cidade)).sort(byName), "Todas");
    options(el("escola"), uniq(all.map((p) => p.escola)).sort(byName), "Todas");
    options(el("idade"), uniq(all.map((p) => p.idade)).sort((a, b) => a - b), "Todas");
    options(el("serie"), uniq(all.map((p) => p.serie)).sort(byName), "Todas");
  }
  F.forEach((k) => el(k).addEventListener(k === "busca" ? "input" : "change", render));
  $("#btn-clear").addEventListener("click", () => {
    F.forEach((k) => { el(k).value = k === "ordem" ? "quente" : ""; });
    render();
  });

  const norm = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  function filtered() {
    const v = Object.fromEntries(F.map((k) => [k, el(k).value]));
    const q = norm(v.busca.trim()), qd = v.busca.replace(/\D/g, "");
    const rows = all.filter((p) =>
      (!q || norm(p.nome).includes(q) || (qd.length >= 3 && p.telefone.includes(qd))) &&
      (!v.cidade || p.cidade === v.cidade) &&
      (!v.escola || p.escola === v.escola) &&
      (!v.idade || String(p.idade) === v.idade) &&
      (!v.serie || p.serie === v.serie) &&
      (!v.contato || p.aceita_contato === (v.contato === "sim")) &&
      (!v.temp || p.temperatura === v.temp) &&
      (!v.conversar || !!p.interesse === (v.conversar === "sim")) &&
      (!v.compart || !!p.compartilhou === (v.compart === "sim")));
    const by = {
      quente: (a, b) => b.pontos - a.pontos || b.criado_em.localeCompare(a.criado_em),
      frio: (a, b) => a.pontos - b.pontos || b.criado_em.localeCompare(a.criado_em),
      recente: (a, b) => b.criado_em.localeCompare(a.criado_em),
      antigo: (a, b) => a.criado_em.localeCompare(b.criado_em),
      nome: (a, b) => a.nome.localeCompare(b.nome, "pt-BR"),
    }[v.ordem];
    // quem não terminou o teste fica sempre no fim nas ordens por temperatura
    if (v.ordem === "quente" || v.ordem === "frio") rows.sort((a, b) => (!a.temperatura - !b.temperatura) || by(a, b));
    else rows.sort(by);
    return rows;
  }

  // ---------------------------------------------------------------- tabela
  let shown = [];
  function render() {
    shown = filtered();
    $("#count").textContent = `${shown.length} de ${all.length} alunos`;
    $("#empty").classList.toggle("hidden", shown.length > 0);
    $("#rows").innerHTML = shown.map((p, i) => `
      <tr data-i="${i}"${p.aceita_contato ? "" : ' class="no-contact" title="Não autorizou contato"'}>
        <td>${tempBadge(p.temperatura)}<small>${p.temperatura ? p.pontos + " pts" : ""}</small></td>
        <td><b>${esc(p.nome)}</b><small>${p.idade ?? "?"} anos</small></td>
        <td class="nowrap"><a href="${waLink(p.telefone)}" target="_blank" rel="noopener">${esc(fmtPhone(p.telefone))}</a></td>
        <td>${esc(p.cidade)}</td>
        <td>${esc(p.escola)}<small>${esc(p.serie)}</small></td>
        <td>${yesNo(p.aceita_contato)}</td>
        <td>${p.cursos.map((c) => esc(c.curso)).join("<br>") || `<small>${STATUS[p.status] || p.status}</small>`}</td>
        <td>${p.interesse ? `<span class="yes">Sim</span><small>${esc(p.interesse.curso)}</small>` : p.clicou_conversar ? `<span class="no">Clicou, não enviou</span>` : yesNo(false)}</td>
        <td class="num">${p.compartilhou ? `<span class="yes">${p.compartilhou}x</span>` : yesNo(false, "", "–")}${p.views_outros ? `<small>abriram ${p.views_outros}x</small>` : ""}</td>
        <td class="num">${p.pdf ? '<span class="yes">Sim</span>' : '<span class="no">–</span>'}</td>
        <td class="num">${p.views_aluno}</td>
        <td class="nowrap">${fmtDate(p.criado_em)}</td>
      </tr>`).join("");
  }
  $("#rows").addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    const tr = e.target.closest("tr[data-i]");
    if (tr) openDetail(shown[+tr.dataset.i]);
  });

  // ---------------------------------------------------------------- detalhe
  const kv = (pairs) => `<dl class="kv">${pairs.filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>`;
  const sec = (title, html) => `<section class="d-sec"><h3>${title}</h3>${html}</section>`;

  function openDetail(p) {
    $("#d-nome").textContent = p.nome;
    $("#d-sub").innerHTML = `${tempBadge(p.temperatura)} ${p.temperatura ? p.pontos + " pontos · " : ""}${esc(STATUS[p.status] || p.status)}`;
    let h = sec("Dados do aluno", kv([
      ["Idade", `${p.idade ?? "?"} anos (nasceu em ${esc(fmtBirth(p.nascimento))})`],
      ["WhatsApp", `<a href="${waLink(p.telefone)}" target="_blank" rel="noopener">${esc(fmtPhone(p.telefone))}</a>`],
      ["Cidade", esc(p.cidade)],
      ["Escola", esc(p.escola)],
      ["Série", esc(p.serie) || "Não informou"],
      ["Autorizou contato", yesNo(p.aceita_contato)],
      ["Começou o teste", fmtDate(p.criado_em)],
      ["Terminou o teste", fmtDate(p.respondido_em) || "Não terminou"],
    ]));
    if (p.perfil.length || p.cursos.length) {
      h += sec("Resultado que apareceu para o aluno",
        (p.perfil.length ? `<p><b>Perfil:</b> ${p.perfil.map(esc).join(", ")}</p>` : "") +
        p.cursos.map((c, i) => `<div class="d-course"><b>${i + 1}. ${esc(c.curso)}</b><p>${esc(c.motivo)}</p></div>`).join("") +
        (p.fonte ? `<p class="small muted">${p.fonte === "llm" ? "Gerado pela IA" : "Conteúdo padrão (a IA não respondeu)"}</p>` : ""));
    }
    h += sec("O que fez na página de resultado", kv([
      ["Vezes que o aluno abriu", String(p.views_aluno)],
      ["Última visita", fmtDate(p.ultima_visita) || "–"],
      ["Compartilhou", p.compartilhou ? `${p.compartilhou}x (${p.compartilhou_como.map((c) => COMO[c] || c).join(", ")})` : yesNo(false)],
      ["Família/amigos abriram o link", p.views_outros ? `${p.views_outros}x` : yesNo(false)],
      ["Salvou em PDF", p.pdf ? `Sim (${p.pdf}x)` : yesNo(false)],
      ["Cursos que abriu", p.cursos_abertos.length ? p.cursos_abertos.map(esc).join(", ") : "Só o primeiro"],
      ["Chamou a Alfabits no WhatsApp", p.clicou_conversar || p.interesse ? "Sim" : yesNo(false)],
    ]));
    if (p.interesse) {
      const it = p.interesse;
      h += sec("Chamou a Alfabits", kv([
        ["Quando", fmtDate(it.em)],
        ["Curso de interesse", esc(it.curso)],
        ["Melhor período", esc(it.periodo)],
        ["Falar com", esc(it.quem)],
        ["Responsável", esc(it.responsavel_nome)],
        ["WhatsApp do responsável", it.responsavel_telefone ? `<a href="${waLink(it.responsavel_telefone)}" target="_blank" rel="noopener">${esc(fmtPhone(it.responsavel_telefone))}</a>` : ""],
        ["Mensagem", esc(it.mensagem)],
      ]));
    }
    if (p.abertas.some((a) => a.resposta)) {
      h += sec("Respostas abertas", p.abertas.map((a) => `<div class="qa"><p>${esc(a.pergunta)}</p><p>${esc(a.resposta) || "–"}</p></div>`).join(""));
    }
    if (p.respostas.length) {
      h += sec(`Respostas do teste (${p.respostas.length})`, `<details><summary>Ver todas as respostas</summary><ul class="answers">${
        p.respostas.map((r) => `<li><span>${esc(r.pergunta)}</span><span>${esc(r.resposta)}</span></li>`).join("")}</ul></details>`);
    }
    h += `<div class="d-actions">
      <a class="a-btn" href="${waLink(p.telefone)}" target="_blank" rel="noopener">Chamar no WhatsApp</a>
      ${p.link ? `<a class="a-btn" href="${esc(p.link)}" target="_blank" rel="noopener">Abrir página de resultado</a>` : ""}
    </div>`;
    $("#d-body").innerHTML = h;
    $("#detail").showModal();
  }
  $("#d-close").addEventListener("click", () => $("#detail").close());
  $("#detail").addEventListener("click", (e) => { if (e.target === e.currentTarget) e.currentTarget.close(); });

  // ---------------------------------------------------------------- planilha e reprocessar
  $("#btn-csv").addEventListener("click", () => {
    const cols = [
      ["Temperatura", (p) => TEMP[p.temperatura] || "Não terminou"], ["Pontos", (p) => p.pontos],
      ["Nome", (p) => p.nome], ["Idade", (p) => p.idade], ["Nascimento", (p) => fmtBirth(p.nascimento)],
      ["WhatsApp", (p) => fmtPhone(p.telefone)], ["Cidade", (p) => p.cidade], ["Escola", (p) => p.escola], ["Série", (p) => p.serie],
      ["Autorizou contato", (p) => (p.aceita_contato ? "sim" : "não")], ["Perfil", (p) => p.perfil.join(", ")],
      ["Cursos sugeridos", (p) => p.cursos.map((c) => c.curso).join(" | ")],
      ["Pediu para conversar", (p) => (p.interesse ? "sim" : "")], ["Curso de interesse", (p) => p.interesse?.curso || ""],
      ["Melhor período", (p) => p.interesse?.periodo || ""], ["Falar com", (p) => p.interesse?.quem || ""],
      ["Responsável", (p) => p.interesse?.responsavel_nome || ""], ["WhatsApp do responsável", (p) => fmtPhone(p.interesse?.responsavel_telefone || "")],
      ["Mensagem", (p) => p.interesse?.mensagem || ""], ["Compartilhou (vezes)", (p) => p.compartilhou],
      ["Família/amigos abriram", (p) => p.views_outros], ["Salvou PDF", (p) => p.pdf], ["Visitas do aluno", (p) => p.views_aluno],
      ["Cursos abertos", (p) => p.cursos_abertos.join(" | ")],
      ["Tempo livre", (p) => p.abertas[0]?.resposta || ""], ["Curso/profissão que pensou", (p) => p.abertas[1]?.resposta || ""],
      ["Status", (p) => STATUS[p.status] || p.status], ["Data", (p) => fmtDate(p.criado_em)],
      ["Link do resultado", (p) => (p.link ? location.origin + p.link : "")],
    ];
    const cell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const csv = [cols.map(([h]) => cell(h)).join(";"), ...shown.map((p) => cols.map(([, fn]) => cell(fn(p))).join(";"))].join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    a.download = `alunos_teste_vocacional_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });

  $("#btn-reproc").addEventListener("click", async () => {
    if (!confirm("Gerar de novo, com a IA, os resultados que ficaram com o conteúdo padrão?")) return;
    const res = await fetch("/api/admin/reprocessar", { method: "POST" });
    if (res.status === 401) return showLogin();
    const out = await res.json().catch(() => ({}));
    alert(out.reprocessando ? `${out.reprocessando} resultado(s) sendo gerados de novo. Clique em Atualizar daqui a pouco.` : "Nenhum resultado para refazer.");
  });

  load();
})();
