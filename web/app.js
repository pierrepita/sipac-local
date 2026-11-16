"use strict";
const token = document.querySelector('meta[name="local-token"]').content;
const $ = id => document.getElementById(id);
let running = false;
let polling = null;
async function api(path, body) {
  const options = {headers: {"X-Local-Token": token}};
  if (body !== undefined) { options.method = "POST"; options.headers["Content-Type"] = "application/json"; options.body = JSON.stringify(body); }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.erro || "Não foi possível concluir a ação.");
  return data;
}
function busy(value) {
  running = value;
  $("iniciar").disabled = value;
  $("escolher").disabled = value;
  $("processo").disabled = value;
  $("destino").disabled = value;
  $("iniciar").textContent = value ? "Consultando e baixando…" : "Consultar e baixar ↓";
}
function draw(state) {
  if (state.status === "pronto") { if (!$("destino").value) $("destino").value = state.destino_padrao; return; }
  $("andamento").hidden = false;
  $("andamento").classList.toggle("error", state.status === "erro");
  $("mensagem").textContent = state.mensagem;
  $("contador").textContent = state.total ? `${state.atual} / ${state.total}` : "";
  if (state.total) { $("progresso").value = state.atual / state.total * 100; }
  else $("progresso").removeAttribute("value");
  $("eventos").replaceChildren(...(state.eventos || []).map(message => { const node = document.createElement("li"); node.textContent = message; return node; }));
  $("resultado").hidden = state.status !== "concluido";
  if (state.status === "concluido") {
    $("salvos").textContent = state.salvos;
    $("arquivos").textContent = state.arquivos;
    $("pendencias").textContent = state.pendencias;
    $("pasta-final").textContent = `Pasta: ${state.pasta}`;
    $("abrir-indice").href = state.indice;
  }
  busy(state.status === "executando");
}
async function refresh() {
  try { draw(await api("/api/estado")); }
  catch (error) { $("mensagem").textContent = "A interface perdeu a conexão. Confira se o terminal do programa continua aberto."; }
  if (running) polling = setTimeout(refresh, 1200);
}
$("form").addEventListener("submit", async event => {
  event.preventDefault();
  const body = {processo: $("processo").value.trim(), destino: $("destino").value.trim()};
  busy(true); $("resultado").hidden = true; $("andamento").hidden = false; $("andamento").classList.remove("error"); $("mensagem").textContent = "Iniciando consulta…";
  if (polling) clearTimeout(polling);
  try { await api("/api/consultar", body); refresh(); }
  catch (error) { busy(false); $("mensagem").textContent = error.message; $("andamento").classList.add("error"); }
});
$("escolher").addEventListener("click", async () => {
  $("escolher").disabled = true;
  try { const result = await api("/api/pasta", {}); if (result.pasta) $("destino").value = result.pasta; }
  catch (error) { $("andamento").hidden = false; $("mensagem").textContent = error.message; }
  finally { $("escolher").disabled = running; }
});
refresh();
