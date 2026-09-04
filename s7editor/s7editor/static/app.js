/* S7 Editor — front da interface local.
   Sem framework e sem CDN: precisa abrir offline, igual à trilha determinística. */
(function () {
  "use strict";

  var BOOT = window.S7_BOOT || {};
  var estado = {
    session: null,
    arquivos: [],
    acao: null,
    jobId: null,
    caixa: null,      // caixa normalizada escolhida na inspeção
    timer: null
  };

  // ---------------------------------------------------------------- utils --
  function $(id) { return document.getElementById(id); }
  function mostrar(el, sim) { if (el) el.classList.toggle("oculto", !sim); }
  function txt(s) { return String(s == null ? "" : s); }

  function el(tag, cls, conteudo) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (conteudo != null) n.textContent = String(conteudo);
    return n;
  }

  function alerta(box, msg, itens) {
    if (!box) return;
    box.textContent = "";
    if (!msg && (!itens || !itens.length)) { mostrar(box, false); return; }
    if (msg) box.appendChild(document.createTextNode(msg));
    if (itens && itens.length) {
      var ul = el("ul");
      itens.slice(0, 8).forEach(function (i) { ul.appendChild(el("li", null, i)); });
      box.appendChild(ul);
    }
    mostrar(box, true);
  }

  function pedir(url, opcoes) {
    return fetch(url, opcoes).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (dados) {
        if (!r.ok) throw new Error(dados.erro || ("falha " + r.status + " em " + url));
        return dados;
      });
    });
  }

  function postJSON(url, corpo) {
    return pedir(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo || {})
    });
  }

  // ----------------------------------------------------------- cabeçalho --
  (function chips() {
    var c = $("chips");
    var ia = el("span", "chip " + (BOOT.has_key ? "on" : "off"),
      BOOT.has_key ? "IA disponível (" + txt(BOOT.image_model) + ")" : "sem OPENAI_API_KEY — só offline");
    c.appendChild(ia);
    c.appendChild(el("span", "chip", "saída: " + txt(BOOT.outbox)));
    c.appendChild(el("span", "chip", "até " + txt(BOOT.max_files) + " imagens por lote"));
  })();

  (function preencheSelects() {
    var papel = $("tt-role");
    var op = el("option", null, "detectar sozinho");
    op.value = "";
    papel.appendChild(op);
    (BOOT.roles || []).forEach(function (r) {
      var o = el("option", null, r);
      o.value = r;
      if (r === "cta") o.selected = true;
      papel.appendChild(o);
    });

    var rotulosReframe = {
      pad: "pad — barras com fundo desfocado (offline)",
      crop: "crop — corta as sobras (offline)",
      outpaint: "outpaint — IA estende o fundo",
      relayout: "relayout — remonta o layout no novo formato"
    };
    var fm = $("fm-mode");
    (BOOT.reframe_modes || ["pad"]).forEach(function (m) {
      var o = el("option", null, rotulosReframe[m] || m);
      o.value = m;
      fm.appendChild(o);
    });

    var rotulosVar = {
      template: "template — remonta a partir das referências (offline)",
      hybrid: "hybrid — fundo por IA, texto redesenhado aqui",
      generative: "generative — cria do zero com IA"
    };
    var vr = $("vr-mode");
    (BOOT.variation_modes || ["generative"]).forEach(function (m) {
      var o = el("option", null, rotulosVar[m] || m);
      o.value = m;
      if (m === (BOOT.has_key ? "generative" : "template")) o.selected = true;
      vr.appendChild(o);
    });

    $("dz-dica").textContent = "ou clique para escolher — " +
      (BOOT.extensions || []).join(" ") + ", até " + txt(BOOT.max_file_mb) + " MB cada";

    atualizaNotas();
  })();

  function atualizaNotas() {
    var m = $("fm-mode").value;
    $("fm-nota").textContent = (m === "outpaint" || m === "relayout")
      ? "Esse modo usa IA (gpt-image-1). O conteúdo original é recolado por cima do resultado — o centro nunca é reescrito pelo modelo."
      : "Modo 100% offline: o conteúdo original entra inteiro, sem distorção; só a área nova é preenchida.";

    var v = $("vr-mode").value;
    $("vr-nota").textContent = (v === "template")
      ? "Modo offline: remonta variações a partir das próprias referências, sem chamar a API."
      : "Esse modo usa IA e consome créditos da sua chave da OpenAI.";
  }
  $("fm-mode").addEventListener("change", atualizaNotas);
  $("vr-mode").addEventListener("change", atualizaNotas);

  // -------------------------------------------------------------- upload --
  var dz = $("dropzone"), input = $("file-input");

  dz.addEventListener("click", function () { input.click(); });
  dz.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });
  ["dragenter", "dragover"].forEach(function (ev) {
    dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add("ativo"); });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove("ativo"); });
  });
  dz.addEventListener("drop", function (e) {
    if (e.dataTransfer && e.dataTransfer.files) enviar(e.dataTransfer.files);
  });
  input.addEventListener("change", function () {
    if (input.files && input.files.length) enviar(input.files);
    input.value = "";
  });

  function enviar(lista) {
    var fd = new FormData();
    var n = 0;
    for (var i = 0; i < lista.length; i++) { fd.append("files", lista[i]); n++; }
    if (!n) return;
    if (estado.session) fd.append("session", estado.session);

    alerta($("upload-erro"), null);
    dz.classList.add("ocupado");
    $("dz-titulo").textContent = "enviando " + n + " arquivo(s)…";

    var restaura = function () {
      dz.classList.remove("ocupado");
      $("dz-titulo").textContent = "Arraste os criativos aqui";
    };

    return pedir("/api/upload", { method: "POST", body: fd })
      .then(function (d) {
        estado.session = d.session;
        estado.arquivos = (estado.arquivos || []).concat(d.files || []);
        desenhaGaleria(d.count);
        alerta($("upload-avisos"), d.warnings && d.warnings.length
          ? "Alguns arquivos ficaram de fora:" : null, d.warnings);
        $("passo-2").classList.remove("desativado");
      })
      .catch(function (e) { alerta($("upload-erro"), e.message); })
      .then(restaura, restaura);
  }

  function desenhaGaleria(total) {
    var g = $("galeria");
    g.textContent = "";
    estado.arquivos.forEach(function (f) {
      var d = el("div", "miniatura");
      var img = el("img");
      img.src = f.preview;
      img.alt = f.name;
      img.loading = "lazy";
      d.appendChild(img);
      d.appendChild(el("span", null, f.name));
      g.appendChild(d);
    });
    $("galeria-contagem").textContent = (total || estado.arquivos.length) + " imagem(ns) na sessão";
    mostrar($("galeria-cab"), true);
    atualizaBotao();
  }

  $("btn-limpar").addEventListener("click", function () {
    estado.session = null; estado.arquivos = []; estado.caixa = null; estado.jobId = null;
    if (estado.timer) { clearInterval(estado.timer); estado.timer = null; }
    $("galeria").textContent = "";
    mostrar($("galeria-cab"), false);
    mostrar($("passo-3"), false);
    mostrar($("passo-4"), false);
    mostrar($("tt-caixa"), false);
    alerta($("upload-avisos"), null);
    alerta($("upload-erro"), null);
    $("passo-2").classList.add("desativado");
    atualizaBotao();
  });

  // --------------------------------------------------------------- ações --
  var botoesAcao = document.querySelectorAll(".acao");
  Array.prototype.forEach.call(botoesAcao, function (b) {
    b.addEventListener("click", function () {
      estado.acao = b.getAttribute("data-acao");
      Array.prototype.forEach.call(botoesAcao, function (o) {
        o.classList.toggle("sel", o === b);
      });
      ["trocar-texto", "formato", "variacoes"].forEach(function (a) {
        mostrar($("form-" + a), a === estado.acao);
      });
      atualizaBotao();
    });
  });

  function atualizaBotao() {
    var pronto = !!(estado.session && estado.arquivos.length && estado.acao);
    $("btn-rodar").disabled = !pronto;
    $("dica-rodar").textContent = !estado.arquivos.length
      ? "Envie as imagens primeiro."
      : (!estado.acao ? "Escolha uma ação acima."
        : "Vai rodar em " + estado.arquivos.length + " imagem(ns).");
  }

  function parametros() {
    if (estado.acao === "trocar-texto") {
      return {
        find: $("tt-find").value.trim(),
        replace: $("tt-replace").value.trim(),
        role: $("tt-role").value,
        box: estado.caixa,
        // Onde o texto procurado não existe, escreve ancorado a outro bloco.
        // É o que faz um lote misto (umas peças com CTA, outras sem) sair
        // inteiro numa passada só.
        else_below: $("tt-else") ? $("tt-else").value : ""
      };
    }
    if (estado.acao === "formato") {
      return {
        target: $("fm-target").value.trim(),
        mode: $("fm-mode").value,
        long_edge: parseInt($("fm-longedge").value, 10) || 1440
      };
    }
    return {
      n: parseInt($("vr-n").value, 10) || 10,
      mode: $("vr-mode").value,
      aspect: $("vr-aspect").value.trim()
    };
  }

  // ---------------------------------------------------------------- lote --
  $("btn-rodar").addEventListener("click", function () {
    alerta($("job-erro"), null);
    $("btn-rodar").disabled = true;
    postJSON("/api/job", {
      session: estado.session, action: estado.acao, params: parametros()
    }).then(function (d) {
      estado.jobId = d.job_id;
      mostrar($("passo-3"), true);
      mostrar($("passo-4"), false);
      mostrar($("btn-baixar"), false);
      mostrar($("btn-relatorio"), false);
      mostrar($("btn-novo"), false);
      mostrar($("resumo"), false);
      alerta($("job-avisos"), null);
      $("resultados").textContent = "";
      $("barra-fill").style.width = "0%";
      $("passo-3").scrollIntoView({ behavior: "smooth", block: "start" });
      acompanhar();
    }).catch(function (e) {
      alerta($("job-erro"), e.message);
      $("btn-rodar").disabled = false;
    });
  });

  function acompanhar() {
    if (estado.timer) clearInterval(estado.timer);
    var puxa = function () {
      pedir("/api/job/" + estado.jobId).then(function (j) {
        $("barra-fill").style.width = j.percent + "%";
        $("status-msg").textContent = j.message || j.status;
        $("status-num").textContent = j.done + " / " + j.total;
        if (j.status === "pronto" || j.status === "erro") {
          clearInterval(estado.timer); estado.timer = null;
          $("btn-rodar").disabled = false;
          mostrar($("btn-novo"), true);
          if (j.status === "erro") {
            alerta($("job-erro"), "O lote falhou: " + j.error);
            $("barra-fill").style.width = "100%";
          } else {
            concluir(j);
          }
        }
      }).catch(function (e) {
        clearInterval(estado.timer); estado.timer = null;
        alerta($("job-erro"), e.message);
        $("btn-rodar").disabled = false;
      });
    };
    puxa();
    estado.timer = setInterval(puxa, 700);
  }

  function cartao(valor, rotulo, cls) {
    var c = el("div", "cartao" + (cls ? " " + cls : ""));
    c.appendChild(el("b", null, valor));
    c.appendChild(el("span", null, rotulo));
    return c;
  }

  function concluir(j) {
    var r = $("resumo");
    r.textContent = "";
    r.appendChild(cartao(j.ok, "prontas", "bom"));
    if (j.failed) r.appendChild(cartao(j.failed, "com erro", "ruim"));
    r.appendChild(cartao(
      j.verified === true ? "0 px" : (j.drift_pixels + " px"),
      "alteração fora das caixas",
      j.verified === true || j.drift_pixels === 0 ? "bom" : "ruim"));
    if (j.cost_usd) r.appendChild(cartao("US$ " + j.cost_usd.toFixed(2), "custo de IA"));
    mostrar(r, true);

    alerta($("job-avisos"), j.warnings && j.warnings.length ? "Avisos do lote:" : null, j.warnings);

    if (j.download) {
      var b = $("btn-baixar");
      b.href = j.download;
      mostrar(b, true);
    }
    if (j.report) {
      var rel = $("btn-relatorio");
      rel.href = j.report;
      mostrar(rel, true);
    }
    desenhaResultados(j.results || []);
  }

  $("btn-novo").addEventListener("click", function () {
    mostrar($("passo-3"), false);
    mostrar($("passo-4"), false);
    $("passo-2").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  function figura(src, legenda) {
    var f = el("figure");
    if (src) {
      var i = el("img");
      i.src = src + (src.indexOf("?") >= 0 ? "&" : "?") + "w=520";
      i.loading = "lazy";
      i.alt = legenda;
      f.appendChild(i);
    } else {
      f.appendChild(el("div", "vazio", "—"));
    }
    f.appendChild(el("figcaption", null, legenda));
    return f;
  }

  function desenhaResultados(linhas) {
    var g = $("resultados");
    g.textContent = "";
    if (!linhas.length) {
      g.appendChild(el("p", "vazio", "Nenhum resultado para mostrar."));
      mostrar($("passo-4"), true);
      return;
    }
    linhas.forEach(function (l) {
      var c = el("div", "res" + (l.ok ? "" : " falhou"));
      var par = el("div", "par");
      par.appendChild(figura(l.before, "antes"));
      par.appendChild(figura(l.after, "depois"));
      c.appendChild(par);

      var pe = el("div", "res-pe");
      pe.appendChild(el("div", "res-nome", l.output_name || l.name));
      var meta = el("div", "res-meta");
      if (l.engine) meta.appendChild(el("span", "selo", l.engine));
      if (l.verified === true && !l.drift_pixels) {
        meta.appendChild(el("span", "selo ok", "0 px fora da caixa"));
      } else if (l.drift_pixels) {
        meta.appendChild(el("span", "selo ruim", l.drift_pixels + " px fora"));
      }
      if (l.duration_s) meta.appendChild(el("span", "selo", l.duration_s + "s"));
      pe.appendChild(meta);
      if (l.error) pe.appendChild(el("div", "res-erro", l.error));
      (l.warnings || []).forEach(function (w) {
        pe.appendChild(el("div", "res-meta", w));
      });
      c.appendChild(pe);
      g.appendChild(c);
    });
    mostrar($("passo-4"), true);
  }

  // ----------------------------------------------------------- inspeção --
  $("btn-inspecionar").addEventListener("click", function () {
    var b = $("btn-inspecionar");
    b.disabled = true;
    b.textContent = "analisando…";
    postJSON("/api/inspect", { session: estado.session, limit: 6 })
      .then(desenhaInspecao)
      .catch(function (e) { alerta($("upload-erro"), e.message); })
      .then(function () { b.disabled = false; b.textContent = "Inspecionar texto"; });
  });

  function desenhaInspecao(d) {
    var corpo = $("modal-corpo");
    corpo.textContent = "";
    $("modal-titulo").textContent = "Inspeção — " + d.analyzed + " de " + d.total + " imagens" +
      (d.offline ? " (offline: acha onde o texto está, não o que está escrito)" : "");

    (d.images || []).forEach(function (im) {
      var linha = el("div", "insp");

      var fig = el("div", "insp-fig");
      var img = el("img");
      img.src = im.preview;
      img.alt = im.name;
      fig.appendChild(img);
      (im.blocks || []).forEach(function (bl) {
        var m = el("div", "marca-caixa");
        m.style.left = (bl.box_norm.x * 100) + "%";
        m.style.top = (bl.box_norm.y * 100) + "%";
        m.style.width = (bl.box_norm.w * 100) + "%";
        m.style.height = (bl.box_norm.h * 100) + "%";
        m.title = "usar esta caixa";
        m.addEventListener("click", function () { usarBloco(bl); });
        fig.appendChild(m);
      });
      linha.appendChild(fig);

      var info = el("div", "insp-info");
      info.appendChild(el("h3", null, im.name));
      info.appendChild(el("div", "vazio",
        im.width + "×" + im.height + " · fundo " + im.background_kind +
        (im.layout ? " · " + im.layout : "")));
      if (im.palette && im.palette.length) {
        var pal = el("div", "paleta");
        im.palette.forEach(function (c) {
          var i = el("i");
          i.style.background = c;
          i.title = c;
          pal.appendChild(i);
        });
        info.appendChild(pal);
      }

      if (!im.blocks || !im.blocks.length) {
        info.appendChild(el("p", "vazio", "Nenhum bloco de texto localizado nesta imagem."));
      } else {
        var t = el("table", "blocos");
        var thead = el("thead");
        var trh = el("tr");
        ["papel", "texto", "tamanho", ""].forEach(function (h) { trh.appendChild(el("th", null, h)); });
        thead.appendChild(trh);
        t.appendChild(thead);
        var tb = el("tbody");
        im.blocks.forEach(function (bl) {
          var tr = el("tr");
          tr.appendChild(el("td", null, bl.role));
          tr.appendChild(el("td", null, bl.text || "(sem OCR)"));
          tr.appendChild(el("td", null, bl.size_px ? bl.size_px + " px" : "—"));
          tr.appendChild(el("td", "usar", "usar caixa →"));
          tr.addEventListener("click", function () { usarBloco(bl); });
          tb.appendChild(tr);
        });
        t.appendChild(tb);
        info.appendChild(t);
      }
      linha.appendChild(info);
      corpo.appendChild(linha);
    });
    mostrar($("modal"), true);
  }

  function usarBloco(bl) {
    estado.caixa = {
      x: bl.box_norm.x, y: bl.box_norm.y,
      w: bl.box_norm.w, h: bl.box_norm.h
    };
    if (bl.text) $("tt-find").value = bl.text;
    if (bl.role) $("tt-role").value = bl.role;
    var c = $("tt-caixa");
    c.textContent = "Caixa escolhida: " +
      [bl.box_norm.x, bl.box_norm.y, bl.box_norm.w, bl.box_norm.h]
        .map(function (v) { return v.toFixed(3); }).join(" · ") +
      "  (normalizada, vale para todas as imagens do lote)";
    var limpar = el("button", "btn-linha", "remover");
    limpar.type = "button";
    limpar.addEventListener("click", function () {
      estado.caixa = null;
      mostrar($("tt-caixa"), false);
    });
    c.appendChild(limpar);
    mostrar(c, true);

    // seleciona a ação de texto para o usuário não precisar voltar
    Array.prototype.forEach.call(botoesAcao, function (b) {
      if (b.getAttribute("data-acao") === "trocar-texto") b.click();
    });
    mostrar($("modal"), false);
    $("tt-replace").focus();
  }

  $("modal-fechar").addEventListener("click", function () { mostrar($("modal"), false); });
  $("modal").addEventListener("click", function (e) {
    if (e.target === $("modal")) mostrar($("modal"), false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") mostrar($("modal"), false);
  });
})();
