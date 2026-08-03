const $ = (id) => document.getElementById(id);
const INTERVALO = 2000;
let timer = null;
let transcricaoDisponivel = false;

async function api(caminho, opcoes = {}) {
  const resposta = await fetch(caminho, opcoes);
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => ({}));
    const erro = new Error(corpo.erro || `erro ${resposta.status}`);
    erro.status = resposta.status;
    throw erro;
  }
  return resposta.status === 204 ? null : resposta.json();
}

function mostrar(autenticado) {
  $("tela-login").hidden = autenticado;
  $("tela-app").hidden = !autenticado;
  if (autenticado) atualizar();
  else clearTimeout(timer);
}

function formatarTamanho(bytes) {
  if (!bytes) return "";
  const mb = bytes / 1048576;
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(1)} MB`;
}

async function transcrever(job) {
  try {
    await api("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: job.url, formato: "transcricao", origem: job.id }),
    });
    atualizar();
  } catch (erro) {
    if (erro.status === 401) mostrar(false);
  }
}

function linha(job) {
  const li = document.createElement("li");
  li.className = `job ${job.status}`;

  const titulo = document.createElement("strong");
  titulo.textContent = job.titulo || job.url;
  li.append(titulo);

  const estado = document.createElement("span");
  estado.className = "estado";
  if (job.status === "pending") estado.textContent = "na fila";
  else if (job.status === "running") estado.textContent = `baixando ${job.progresso}%`;
  else if (job.status === "expired") estado.textContent = "expirado";
  else if (job.status === "error") estado.textContent = job.erro_de_cookies
    ? "cookies expirados — envie um cookies.txt novo abaixo"
    : job.erro;
  else estado.textContent = formatarTamanho(job.tamanho);
  li.append(estado);

  if (job.status === "ready") {
    const acoes = document.createElement("div");
    acoes.className = "acoes";

    const link = document.createElement("a");
    link.href = `/api/jobs/${job.id}/file`;
    link.textContent = "Baixar";
    link.className = "baixar";
    acoes.append(link);

    if ((job.formato === "video" || job.formato === "audio") && transcricaoDisponivel) {
      const botao = document.createElement("button");
      botao.type = "button";
      botao.className = "transcrever";
      botao.textContent = "Transcrever";
      botao.addEventListener("click", () => transcrever(job));
      acoes.append(botao);
    }
    li.append(acoes);

    if (job.formato === "transcricao" && typeof job.transcricao_texto === "string") {
      const detalhes = document.createElement("details");
      detalhes.className = "transcricao-texto";
      const resumo = document.createElement("summary");
      resumo.textContent = "Ver transcrição";
      detalhes.append(resumo);

      const texto = document.createElement("pre");
      texto.textContent = job.transcricao_texto;
      detalhes.append(texto);

      const copiar = document.createElement("button");
      copiar.type = "button";
      copiar.className = "copiar";
      copiar.textContent = "Copiar";
      copiar.addEventListener("click", async () => {
        await navigator.clipboard.writeText(job.transcricao_texto);
        copiar.textContent = "Copiado!";
        setTimeout(() => { copiar.textContent = "Copiar"; }, 1500);
      });
      detalhes.append(copiar);

      li.append(detalhes);
    }
  }
  return li;
}

async function atualizar() {
  clearTimeout(timer);
  try {
    const dados = await api("/api/jobs");
    const lista = $("lista");
    lista.replaceChildren(...dados.jobs.map(linha));
    $("cookies-data").textContent = dados.cookies_atualizados_em
      ? `· atualizados em ${new Date(dados.cookies_atualizados_em * 1000).toLocaleString("pt-BR")}`
      : "· nunca enviados";
    const ativo = dados.jobs.some((j) => j.status === "pending" || j.status === "running");
    timer = setTimeout(atualizar, ativo ? INTERVALO : INTERVALO * 5);
  } catch (erro) {
    if (erro.status === 401) mostrar(false);
    else timer = setTimeout(atualizar, INTERVALO * 5);
  }
}

$("form-login").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const aviso = $("erro-login");
  aviso.hidden = true;
  try {
    await api("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ senha: $("senha").value }),
    });
    $("senha").value = "";
    mostrar(true);
  } catch (erro) {
    aviso.textContent = erro.message;
    aviso.hidden = false;
  }
});

$("form-job").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const aviso = $("erro-job");
  aviso.hidden = true;
  const formato = document.querySelector('input[name="formato"]:checked').value;
  try {
    await api("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: $("url").value, formato }),
    });
    $("url").value = "";
    atualizar();
  } catch (erro) {
    if (erro.status === 401) {
      mostrar(false);
      return;
    }
    aviso.textContent = erro.message;
    aviso.hidden = false;
  }
});

$("arquivo-cookies").addEventListener("change", async (evento) => {
  const arquivo = evento.target.files[0];
  if (!arquivo) return;
  const aviso = $("erro-cookies");
  aviso.hidden = true;
  const dados = new FormData();
  dados.append("arquivo", arquivo);
  try {
    const resultado = await api("/api/cookies", { method: "POST", body: dados });
    const detalhes = [];
    if (resultado.corrigidos) detalhes.push(`${resultado.corrigidos} corrigido${resultado.corrigidos === 1 ? "" : "s"}`);
    if (resultado.descartados) detalhes.push(`${resultado.descartados} descartado${resultado.descartados === 1 ? "" : "s"}`);
    aviso.textContent = `${resultado.cookies} cookies enviados${detalhes.length ? ` (${detalhes.join(", ")})` : ""}.`;
    aviso.className = "ok";
    aviso.hidden = false;
    atualizar();
  } catch (erro) {
    if (erro.status === 401) {
      mostrar(false);
      return;
    }
    aviso.textContent = erro.message;
    aviso.className = "erro";
    aviso.hidden = false;
  } finally {
    evento.target.value = "";
  }
});

$("sair").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  mostrar(false);
});

api("/api/session").then((dados) => {
  mostrar(dados.autenticado);
  $("versao").textContent = `inemadlp v${dados.versao}`;
  transcricaoDisponivel = !!dados.transcricao_disponivel;
  $("opcao-transcricao").hidden = !transcricaoDisponivel;
});
