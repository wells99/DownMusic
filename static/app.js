const form = document.querySelector("#download-form");
const submitButton = document.querySelector("#submit-button");
const formError = document.querySelector("#form-error");
const jobsElement = document.querySelector("#jobs");
const filesElement = document.querySelector("#files");

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
}
function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
function statusLabel(status) {
  return ({queued:"Na fila",downloading:"Em andamento",done:"Concluído",error:"Falhou"})[status] || status;
}
async function refresh() {
  try {
    const [jobsResponse, filesResponse] = await Promise.all([fetch("/api/jobs"), fetch("/api/files")]);
    if (!jobsResponse.ok || !filesResponse.ok) return;
    const jobs = await jobsResponse.json();
    const files = await filesResponse.json();
    const pending = jobs.filter((job) => ["queued", "downloading"].includes(job.status)).length;
    document.querySelector("#queue-count").textContent = `${pending} ${pending === 1 ? "ativo" : "ativos"}`;
    document.querySelector("#file-count").textContent = `${files.length} ${files.length === 1 ? "arquivo" : "arquivos"}`;
    jobsElement.innerHTML = jobs.length ? jobs.map((job) => {
      const title = job.current_title || job.url;
      const outputs = (job.outputs || []).map((path) => `<a href="/files/${path.split("/").map(encodeURIComponent).join("/")}">♫ ${escapeHtml(path)}</a>`).join("");
      const itemCount = job.total_count ? `${job.current_index || 0}/${job.total_count} itens` : "";
      const transfer = job.wait_seconds > 0 ? `Faltam ${job.wait_seconds} s` : [job.progress, job.speed].filter(Boolean).join(" · ");
      const detail = [job.phase, itemCount, transfer].filter(Boolean).join(" · ");
      const errors = job.status === "error" && job.errors?.length ? `<ul class="job-errors">${job.errors.map((error) => `<li>${escapeHtml(error)}</li>`).join("")}</ul>` : "";
      return `<article class="job-card"><div class="job-top"><div><div class="job-title">${escapeHtml(title)}</div><div class="job-phase">${escapeHtml(detail || "Aguardando")}</div></div><span class="status ${escapeHtml(job.status)}">${escapeHtml(statusLabel(job.status))}</span></div>${job.status === "error" && job.error ? `<div class="job-error">${escapeHtml(job.error)}</div>` : ""}${errors}${outputs ? `<div class="output-links">${outputs}</div>` : ""}</article>`;
    }).join("") : `<div class="empty-state"><span>♫</span><p>Seus downloads vão aparecer aqui.</p></div>`;
    filesElement.innerHTML = files.length ? files.map((file) => `<div class="file-row"><div><div class="file-name">♫ ${escapeHtml(file.name)}</div><div class="file-path">${escapeHtml(file.path)}</div></div><a class="file-size" href="/files/${file.path.split("/").map(encodeURIComponent).join("/")}">${formatSize(file.size)} ↓</a></div>`).join("") : `<div class="empty-state compact"><p>Nenhum MP3 salvo ainda.</p></div>`;
  } catch (_) {
    // A atualização seguinte tenta novamente se o servidor reiniciar.
  }
}
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.textContent = "";
  submitButton.disabled = true;
  submitButton.querySelector("span:first-child").textContent = "Adicionando à fila…";
  try {
    const response = await fetch("/api/jobs", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(Object.fromEntries(new FormData(form)))});
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "Não foi possível iniciar o download.");
    form.reset();
    await refresh();
  } catch (error) {
    formError.textContent = error.message;
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector("span:first-child").textContent = "Baixar áudio";
  }
});
refresh();
setInterval(refresh, 2500);
