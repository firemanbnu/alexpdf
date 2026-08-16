(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  let token = localStorage.getItem("token") || null;
  let subjectsMap = {}; // id -> {id, nome, keywords}
  let currentDoc = null;
  let analysis = null; // resultado da análise exibido

  const authView = $("#auth-view");
  const appView = $("#app-view");

  // ------------------------------------------------------------ helpers
  async function api(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (opts.body && !(opts.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }
    const res = await fetch(path, { ...opts, headers });
    if (res.status === 401) {
      logout();
      throw new Error("Sessão expirada. Entre novamente.");
    }
    const isJson = res.headers.get("content-type")?.includes("application/json");
    const data = isJson ? await res.json() : null;
    if (!res.ok) {
      let msg = data?.detail || `Erro ${res.status}`;
      if (typeof msg === "object") msg = JSON.stringify(msg);
      throw new Error(msg);
    }
    return data;
  }

  function toast(msg, isError = false) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.toggle("error", isError);
    t.classList.remove("hidden");
    clearTimeout(t._timer);
    t._timer = setTimeout(() => t.classList.add("hidden"), 3500);
  }

  function fmtDate(s) {
    if (!s) return "";
    const d = new Date(s);
    return d.toLocaleDateString("pt-BR") + " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  }

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // ------------------------------------------------------------ auth
  function showView(kind) {
    if (kind === "auth") {
      authView.classList.remove("hidden");
      appView.classList.add("hidden");
    } else {
      authView.classList.add("hidden");
      appView.classList.remove("hidden");
    }
  }

  function setTab(name) {
    $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
    $$(".view").forEach((v) => v.classList.add("hidden"));
    $("#view-" + name).classList.remove("hidden");
  }

  function logout() {
    token = null;
    localStorage.removeItem("token");
    showView("auth");
  }

  function goAuthMode(mode) {
    const isLogin = mode === "login";
    $("#tab-login").classList.toggle("active", isLogin);
    $("#tab-register").classList.toggle("active", !isLogin);
    $("#field-nome").classList.toggle("hidden", isLogin);
    $("#auth-submit").textContent = isLogin ? "Entrar" : "Cadastrar";
    $("#auth-error").classList.add("hidden");
  }

  async function submitAuth(e) {
    e.preventDefault();
    const email = $("#email").value.trim();
    const senha = $("#senha").value;
    const isLogin = $("#tab-login").classList.contains("active");
    try {
      if (isLogin) {
        const body = new URLSearchParams({ username: email, password: senha });
        const res = await api("/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body,
        });
        token = res.access_token;
        localStorage.setItem("token", token);
      } else {
        const nome = $("#nome").value.trim();
        await api("/auth/register", {
          method: "POST",
          body: JSON.stringify({ nome, email, senha }),
        });
        toast("Cadastro feito! Agora entre com seu e-mail e senha.");
        goAuthMode("login");
        return;
      }
      enterApp();
    } catch (err) {
      const el = $("#auth-error");
      el.textContent = err.message;
      el.classList.remove("hidden");
    }
  }

  async function enterApp() {
    showView("app");
    const me = await api("/auth/me").catch(() => null);
    $("#user-name").textContent = me ? me.nome : "";
    await loadSubjects();
    await loadDocuments();
    setTab("documents");
  }

  // ------------------------------------------------------------ subjects
  async function loadSubjects() {
    const list = await api("/subjects");
    subjectsMap = {};
    list.forEach((s) => (subjectsMap[s.id] = s));
    renderSubjects();
  }

  function renderSubjects() {
    const wrap = $("#subjects-list");
    const empty = $("#subjects-empty");
    const list = Object.values(subjectsMap);
    empty.classList.toggle("hidden", list.length > 0);
    wrap.innerHTML = list
      .map(
        (s) => `
        <div class="subject-item" data-id="${s.id}">
          <div>
            <h4>${esc(s.nome)}</h4>
            <div class="chips">${s.keywords.map((k) => `<span class="chip">${esc(k.palavra)}</span>`).join("") || '<span class="muted">sem palavras-chave</span>'}</div>
          </div>
          <div class="subject-actions">
            <input type="text" class="edit-name" placeholder="Novo nome" value="${esc(s.nome)}">
            <input type="text" class="edit-kw" placeholder="Novas palavras-chave" value="${esc(s.keywords.map((k) => k.palavra).join(", "))}">
            <button class="btn save">Salvar</button>
            <button class="btn danger del">Excluir</button>
          </div>
        </div>`
      )
      .join("");
  }

  // ------------------------------------------------------------ documents
  async function loadDocuments() {
    const list = await api("/documents");
    const empty = $("#docs-empty");
    const table = $("#docs-table");
    const body = $("#docs-body");
    empty.classList.toggle("hidden", list.length > 0);
    table.hidden = list.length === 0;
    body.innerHTML = list
      .map(
        (d) => `
        <tr data-id="${d.id}">
          <td>${esc(d.nome_original)}</td>
          <td>${d.num_paginas}</td>
          <td>${fmtDate(d.criado_em)}</td>
          <td>
            <button class="btn analyze">Analisar</button>
            <button class="btn danger del">Excluir</button>
          </td>
        </tr>`
      )
      .join("");
  }

  async function uploadFiles(files) {
    if (!files.length) return;
    const btn = $("#btn-upload");
    btn.disabled = true;
    try {
      for (const f of files) {
        const form = new FormData();
        form.append("file", f);
        await api("/documents/upload", { method: "POST", body: form });
        toast(`“${f.name}” enviado`);
      }
      await loadDocuments();
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false;
      $("#file-input").value = "";
    }
  }

  // ------------------------------------------------------------ analysis
  async function openAnalysis(docId) {
    currentDoc = { id: docId };
    const list = await api("/documents");
    const doc = list.find((d) => d.id === docId);
    if (!doc) return;
    currentDoc.nome = doc.nome_original;
    $("#analyze-title").textContent = "Análise de páginas";
    $("#analyze-doc-info").textContent = `${doc.nome_original} — ${doc.num_paginas} páginas`;
    $("#analysis-body").innerHTML = "";
    $("#analysis-empty").classList.remove("hidden");
    $("#results-box").classList.add("hidden");
    $("#analyze-msg").classList.add("hidden");
    setTab("analyze");
    await runAnalysis(false);
  }

  async function runAnalysis(showError = true) {
    if (!currentDoc) return;
    try {
      analysis = await api(`/extract/analyze/${currentDoc.id}`, { method: "POST" });
      renderAnalysis();
      toast("Análise concluída. Revise a seleção e extraia.");
    } catch (err) {
      if (showError) toast(err.message, true);
      else {
        $("#analyze-msg").textContent = err.message;
        $("#analyze-msg").classList.remove("hidden");
      }
    }
  }

  function renderAnalysis() {
    $("#analysis-empty").classList.add("hidden");
    const body = $("#analysis-body");
    const subjOptions = Object.values(subjectsMap).map((s) => `<option value="${s.id}">${esc(s.nome)}</option>`).join("");
    body.innerHTML = analysis.paginas
      .map((p) => {
        const confirmed = p.matches.find((m) => m.confirmada);
        const selectedId = confirmed ? confirmed.subject_id : "";
        const scores = p.matches
          .map(
            (m) =>
              `<span><strong>${esc(subjectsMap[m.subject_id]?.nome || "?")}:</strong> ${m.score}${m.confirmada ? " ✓" : ""}</span>`
          )
          .join("") || '<span>—</span>';
        return `
          <tr data-page="${p.num_pagina}">
            <td><strong>${p.num_pagina}</strong></td>
            <td class="preview">${esc(p.texto_preview) || "(sem texto)"}</td>
            <td>
              <select class="page-subject">
                <option value="">— Nenhum —</option>
                ${subjOptions}
              </select>
            </td>
            <td><div class="score-list">${scores}</div></td>
          </tr>`;
      })
      .join("");
    $$("#analysis-body select.page-subject").forEach((sel, i) => {
      const confirmed = analysis.paginas[i].matches.find((m) => m.confirmada);
      if (confirmed) sel.value = String(confirmed.subject_id);
      sel.addEventListener("change", () => markPage(sel, i));
    });
  }

  function markPage(sel, idx) {
    const page = analysis.paginas[idx];
    page.matches.forEach((m) => {
      m.confirmada = String(m.subject_id) === sel.value;
    });
    renderAnalysis();
  }

  async function saveSelection() {
    if (!currentDoc) return;
    const items = [];
    $$("#analysis-body select.page-subject").forEach((sel, i) => {
      if (sel.value) {
        items.push({
          subject_id: Number(sel.value),
          num_pagina: analysis.paginas[i].num_pagina,
          confirmada: true,
        });
      }
    });
    try {
      analysis = await api(`/extract/confirm/${currentDoc.id}`, {
        method: "POST",
        body: JSON.stringify({ items }),
      });
      renderAnalysis();
      toast("Seleção salva");
    } catch (err) {
      toast(err.message, true);
    }
  }

  async function extractPages() {
    if (!currentDoc) return;
    try {
      const res = await api(`/extract/run/${currentDoc.id}`, { method: "POST" });
      const box = $("#results-box");
      $("#results-list").innerHTML = res.arquivos
        .map(
          (f) =>
            `<li>${f.endsWith(".zip") ? "" : ""}<a href="/extract/download/${encodeURIComponent(f)}" download>${esc(f)}</a>${f.endsWith(".zip") ? " (todos em ZIP)" : ""}</li>`
        )
        .join("");
      box.classList.remove("hidden");
      toast("Arquivos gerados com sucesso");
    } catch (err) {
      toast(err.message, true);
    }
  }

  // ------------------------------------------------------------ events
  $("#tab-login").addEventListener("click", () => goAuthMode("login"));
  $("#tab-register").addEventListener("click", () => goAuthMode("register"));
  $("#auth-form").addEventListener("submit", submitAuth);
  $("#logout").addEventListener("click", logout);

  $("#subject-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const nome = $("#subject-name").value.trim();
    const keywords = $("#subject-keywords").value.split(",").map((s) => s.trim()).filter(Boolean);
    if (!nome) return;
    try {
      await api("/subjects", { method: "POST", body: JSON.stringify({ nome, keywords }) });
      $("#subject-name").value = "";
      $("#subject-keywords").value = "";
      await loadSubjects();
      toast("Assunto adicionado");
    } catch (err) {
      toast(err.message, true);
    }
  });

  $("#subjects-list").addEventListener("click", async (e) => {
    const item = e.target.closest(".subject-item");
    if (!item) return;
    const id = Number(item.dataset.id);
    if (e.target.classList.contains("del")) {
      try {
        await api(`/subjects/${id}`, { method: "DELETE" });
        await loadSubjects();
        toast("Assunto excluído");
      } catch (err) {
        toast(err.message, true);
      }
    } else if (e.target.classList.contains("save")) {
      const nome = item.querySelector(".edit-name").value.trim();
      const keywords = item.querySelector(".edit-kw").value.split(",").map((s) => s.trim()).filter(Boolean);
      if (!nome) return;
      try {
        await api(`/subjects/${id}`, { method: "PUT", body: JSON.stringify({ nome, keywords }) });
        await loadSubjects();
        toast("Assunto atualizado");
      } catch (err) {
        toast(err.message, true);
      }
    }
  });

  $("#btn-upload").addEventListener("click", () => uploadFiles($("#file-input").files));
  $("#file-input").addEventListener("change", (e) => uploadFiles(e.target.files));

  $("#docs-body").addEventListener("click", async (e) => {
    const tr = e.target.closest("tr");
    if (!tr) return;
    const id = Number(tr.dataset.id);
    if (e.target.classList.contains("analyze")) {
      openAnalysis(id);
    } else if (e.target.classList.contains("del")) {
      try {
        await api(`/documents/${id}`, { method: "DELETE" });
        await loadDocuments();
        toast("Documento excluído");
      } catch (err) {
        toast(err.message, true);
      }
    }
  });

  $("#btn-analyze").addEventListener("click", () => runAnalysis());
  $("#btn-save").addEventListener("click", saveSelection);
  $("#btn-extract").addEventListener("click", extractPages);

  $$(".nav-btn").forEach((b) =>
    b.addEventListener("click", () => {
      setTab(b.dataset.view);
      if (b.dataset.view === "documents") loadDocuments();
      if (b.dataset.view === "subjects") loadSubjects();
    })
  );

  // ------------------------------------------------------------ init
  async function init() {
    if (token) {
      try {
        await enterApp();
        return;
      } catch (err) {
        logout();
      }
    }
    showView("auth");
  }

  init();
})();
