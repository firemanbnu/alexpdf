(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  let token = localStorage.getItem("token") || null;
  let currentDoc = null; // { id, nome, num_paginas }
  let analysis = null; // resultado da análise exibido

  const authView = $("#auth-view");
  const appView = $("#app-view");

  // ------------------------------------------------------------ helpers
  async function api(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (opts.body && !(opts.body instanceof FormData) && !(opts.body instanceof URLSearchParams)) {
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

  // ------------------------------------------------------------ auth / nav
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
    currentDoc = null;
    analysis = null;
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
    await loadDocuments();
    setTab("documents");
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
    const list = await api("/documents");
    const doc = list.find((d) => d.id === docId);
    if (!doc) return;
    currentDoc = { id: doc.id, nome: doc.nome_original, num_paginas: doc.num_paginas };
    $("#analyze-title").textContent = "Separação por nome";
    $("#analyze-doc-info").textContent = `${doc.nome_original} — ${doc.num_paginas} páginas`;
    $("#results-box").classList.add("hidden");
    $("#analyze-msg").classList.add("hidden");
    setTab("analyze");
    await runAnalysis(false);
  }

  async function runAnalysis(showError = true) {
    if (!currentDoc) return;
    const loading = $("#analyze-loading");
    const empty = $("#analysis-empty");
    const msg = $("#analyze-msg");
    loading.classList.remove("hidden");
    empty.classList.add("hidden");
    msg.classList.add("hidden");
    $("#persons-list").innerHTML = "";
    try {
      analysis = await api(`/extract/analyze/${currentDoc.id}`, { method: "POST" });
      renderAnalysis();
      toast("Análise concluída. Desmarque páginas indesejadas e extraia.");
    } catch (err) {
      if (showError) toast(err.message, true);
      else {
        msg.textContent = err.message;
        msg.classList.remove("hidden");
      }
    } finally {
      loading.classList.add("hidden");
    }
  }

  function renderAnalysis() {
    const wrap = $("#persons-list");
    const empty = $("#analysis-empty");
    empty.classList.toggle("hidden", (analysis.pessoas || []).length > 0);

    wrap.innerHTML = (analysis.pessoas || [])
      .map((p) => {
        const total = p.paginas.length;
        const confirmadas = p.paginas.filter((pg) => pg.confirmada).length;
        const datas = p.paginas.map((pg) => pg.data_sessao).filter(Boolean);
        const periodo = datas.length
          ? `${datas[0]} a ${datas[datas.length - 1]}`
          : "—";
        const rows = p.paginas
          .map(
            (pg) => `
            <tr>
              <td><input type="checkbox" class="page-check" data-page="${pg.num_pagina}" ${pg.confirmada ? "checked" : ""}></td>
              <td><strong>${pg.num_pagina}</strong></td>
              <td>${esc(pg.data_sessao || "—")}</td>
              <td>${esc(pg.hora_inicio || "—")}</td>
            </tr>`
          )
          .join("");
        return `
          <details class="person" data-person="${p.person_id}" ${confirmadas === total ? "" : "open"}>
            <summary>
              <span class="person-name">${esc(p.nome)}</span>
              <span class="person-meta">${confirmadas}/${total} páginas · ${esc(periodo)}</span>
            </summary>
            <table class="table pages">
              <thead><tr><th>Incluir</th><th>Pág.</th><th>Data</th><th>Início</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </details>`;
      })
      .join("");

    if (!(analysis.pessoas || []).length) {
      empty.textContent =
        "Nenhuma assinatura APOC com nome foi encontrada neste documento. Verifique se o arquivo tem o campo APOC com nome à direita.";
      empty.classList.remove("hidden");
    }
  }

  async function saveSelection() {
    if (!currentDoc || !analysis) return;
    const items = [];
    $$("#persons-list details.person").forEach((det) => {
      const personId = Number(det.dataset.person);
      det.querySelectorAll(".page-check").forEach((cb) => {
        items.push({
          person_id: personId,
          num_pagina: Number(cb.dataset.page),
          confirmada: cb.checked,
        });
      });
    });
    try {
      analysis = await api(`/extract/confirm/${currentDoc.id}`, {
        method: "POST",
        body: JSON.stringify({ items }),
      });
      renderAnalysis();
    } catch (err) {
      toast(err.message, true);
    }
  }

  async function extractPages() {
    if (!currentDoc) return;
    try {
      const res = await api(`/extract/run/${currentDoc.id}`, { method: "POST" });
      const box = $("#results-box");
      let html = "";
      const arquivo = (res.compilado_url || "").split("/").pop() || (res.arquivos && res.arquivos[0]) || "";
      if (arquivo) {
        html = `<li class="compilado-link"><a href="#" class="download-link" data-file="${esc(arquivo)}">${esc(arquivo)}</a></li>`;
      }
      $("#results-list").innerHTML = html;
      box.classList.remove("hidden");
      toast("PDF gerado com sucesso");
    } catch (err) {
      toast(err.message, true);
    }
  }

  async function downloadFile(filename) {
    try {
      const res = await fetch(`/extract/download/${encodeURIComponent(filename)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) { logout(); return; }
      if (!res.ok) { toast("Erro ao baixar arquivo", true); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast(err.message, true);
    }
  }

  // ------------------------------------------------------------ events
  $("#tab-login").addEventListener("click", () => goAuthMode("login"));
  $("#tab-register").addEventListener("click", () => goAuthMode("register"));
  $("#auth-form").addEventListener("submit", submitAuth);
  $("#logout").addEventListener("click", logout);

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
  $("#btn-back").addEventListener("click", () => {
    currentDoc = null;
    analysis = null;
    setTab("documents");
    loadDocuments();
  });
  $("#btn-extract").addEventListener("click", extractPages);
  $("#results-list").addEventListener("click", (e) => {
    const link = e.target.closest(".download-link");
    if (link) { e.preventDefault(); downloadFile(link.dataset.file); }
  });

  $("#persons-list").addEventListener("change", (e) => {
    if (e.target.classList.contains("page-check")) saveSelection();
  });

  $$(".nav-btn").forEach((b) =>
    b.addEventListener("click", () => {
      setTab(b.dataset.view);
      if (b.dataset.view === "documents") loadDocuments();
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
