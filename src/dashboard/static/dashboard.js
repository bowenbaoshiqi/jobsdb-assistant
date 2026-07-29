const elements = {
  list: document.querySelector("#job-list"),
  error: document.querySelector("#dashboard-error"),
  status: document.querySelector("#dashboard-status"),
  selectedCount: document.querySelector("#selected-count"),
  totalCount: document.querySelector("#total-count"),
  evaluatedCount: document.querySelector("#evaluated-count"),
  pendingCount: document.querySelector("#pending-count"),
  show: document.querySelector("#show-filter"),
  score: document.querySelector("#score-filter"),
  type: document.querySelector("#type-filter"),
  selection: document.querySelector("#selection-filter"),
  query: document.querySelector("#query-filter"),
  dialog: document.querySelector("#apply-confirmation"),
  confirmationJob: document.querySelector("#confirmation-job"),
  confirmApply: document.querySelector("#confirm-apply"),
  progressStatus: document.querySelector("#progress-status"),
  progressNote: document.querySelector("#progress-note"),
  progressTotal: document.querySelector("#progress-total"),
  progressQueued: document.querySelector("#progress-queued"),
  progressRunning: document.querySelector("#progress-running"),
  progressCompleted: document.querySelector("#progress-completed"),
  progressFailed: document.querySelector("#progress-failed"),
  refreshResults: document.querySelector("#refresh-results"),
  generateCoverLetters: document.querySelector("#generate-cover-letters"),
  generateFullMaterials: document.querySelector("#generate-full-materials"),
  materialBatchStatus: document.querySelector("#material-batch-status"),
  materialBatchNote: document.querySelector("#material-batch-note"),
  nextBatchKeyword: document.querySelector("#next-batch-keyword"),
  archiveAndDiscover: document.querySelector("#archive-and-discover"),
  refreshBatchStatus: document.querySelector("#refresh-batch-status"),
  batchStatus: document.querySelector("#batch-status"),
};

let currentPage = null;
let pendingApplyJob = null;

function setMaterialButtonsDisabled(disabled) {
  elements.generateCoverLetters.disabled = disabled;
  elements.generateFullMaterials.disabled = disabled;
}

function text(tag, value, className = "") {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
}

function listBlock(title, items) {
  const section = document.createElement("section");
  section.append(text("h3", title));
  const list = document.createElement("ul");
  const values = items.length ? items : ["—"];
  values.forEach((item) => list.append(text("li", item)));
  section.append(list);
  return section;
}

function setError(message = "") {
  elements.error.textContent = message;
  elements.error.hidden = !message;
}

function setStatus(message) {
  elements.status.textContent = message;
}

function filtersFromUrl() {
  const params = new URLSearchParams(window.location.search);
  elements.show.checked = params.get("show") === "all";
  elements.score.value = params.get("score_min") || "";
  elements.type.value = params.get("apply_type") || "";
  elements.selection.value = params.get("selected") || "";
  elements.query.value = params.get("query") || "";
}

function updateUrlFromFilters() {
  const params = new URLSearchParams();
  if (elements.show.checked) params.set("show", "all");
  if (elements.score.value) params.set("score_min", elements.score.value);
  if (elements.type.value) params.set("apply_type", elements.type.value);
  if (elements.selection.value) params.set("selected", elements.selection.value);
  if (elements.query.value.trim()) params.set("query", elements.query.value.trim());
  const query = params.toString();
  history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
}

function queryForApi() {
  return window.location.search || "";
}

function renderTrace(job) {
  const details = document.createElement("details");
  details.append(text("summary", "查看评分过程"));
  const trace = document.createElement("div");
  trace.className = "trace";

  if (job.evaluation_status === "pending") {
    trace.append(text("p", "该职位尚无已保存的结构化评分。"));
  } else {
    job.dimensions.forEach((dimension) => {
      const block = document.createElement("section");
      block.className = "dimension-block";
      const score = dimension.score === null ? "—" : `${dimension.score.toFixed(1)} / 5`;
      block.append(text("h3", `${dimension.code} · ${dimension.title} · ${score}`));
      block.append(listBlock("评分结论", dimension.findings));
      block.append(listBlock("依据", dimension.evidence));
      trace.append(block);
    });
  }

  const verdict = text(
    "p",
    "当前没有逐条画像要求的独立结构化判定，请结合已保存的 A–F 评分依据人工检查。",
    "muted",
  );
  trace.append(verdict);

  if (job.profile_summary) {
    const profile = document.createElement("section");
    profile.className = "profile-summary";
    profile.append(text("h3", `候选人画像 v${job.profile_summary.profile_version}`));
    profile.append(text("p", `目标职位：${job.profile_summary.target_roles.join(", ") || "—"}`));
    profile.append(text("p", `求职偏好：${JSON.stringify(job.profile_summary.preferences)}`));
    profile.append(text("p", `排除条件：${job.profile_summary.exclusions.join("; ") || "—"}`));
    trace.append(profile);
  }

  if (job.provenance) {
    const provenance = document.createElement("section");
    provenance.className = "provenance";
    provenance.append(text("h3", "评分溯源"));
    provenance.append(text("p", `评分记录：${job.provenance.evaluation_id}`));
    provenance.append(text("p", `画像版本：${job.provenance.profile_version}`));
    provenance.append(text("p", `JD 快照：${job.provenance.snapshot_id}`));
    provenance.append(text("p", `Career Ops 版本：${job.provenance.engine_commit || "—"}`));
    provenance.append(text("p", `评分协议：${job.provenance.prompt_version}`));
    trace.append(provenance);
  }

  const jd = document.createElement("section");
  jd.className = "jd";
  jd.append(text(
    "h3",
    job.evaluation_status === "evaluated"
      ? "职位描述（简体中文摘要）"
      : "当前职位描述",
  ));
  jd.append(text("pre", job.jd_text));
  trace.append(jd);
  details.append(trace);
  return details;
}

function renderActions(job, checkbox) {
  const actions = document.createElement("div");
  actions.className = "job-actions";

  const open = text("a", "打开 JobsDB", "button-link");
  open.href = job.canonical_url;
  open.target = "_blank";
  open.rel = "noopener noreferrer";
  actions.append(open);

  if (job.apply_type === "quick_apply") {
    const direct = text("button", "使用默认简历直接投递");
    direct.type = "button";
    direct.disabled = ["applying", "submitted", "skipped_already_applied"].includes(
      job.application_task?.status,
    );
    if (job.application_task?.status === "applying") direct.textContent = "投递中…";
    if (job.application_task?.status === "submitted") direct.textContent = "已投递";
    direct.addEventListener("click", () => {
      pendingApplyJob = { job, button: direct };
      elements.confirmationJob.textContent = `确认投递 ${job.company} 的 ${job.title}？`;
      elements.dialog.showModal();
    });
    actions.append(direct);
  } else {
    const manual = text("a", "打开职位并人工投递", "button-link");
    manual.href = job.canonical_url;
    manual.target = "_blank";
    manual.rel = "noopener noreferrer";
    actions.append(manual);
  }

  if (job.material?.package_id) {
    const preview = text("a", `预览定制材料 v${job.material.version}`, "button-link primary");
    preview.href = `/materials/${encodeURIComponent(job.material.package_id)}`;
    actions.append(preview);
    const approved = ["approved", "approved_with_fact_override"].includes(
      job.material.review_status,
    );
    const execution = job.approved_application;
    if (approved && job.apply_type === "quick_apply") {
      if (execution?.status === "waiting_for_confirmation") {
        const confirm = text("button", "确认并提交申请", "primary");
        confirm.type = "button";
        confirm.addEventListener("click", () => confirmApproved(execution, confirm));
        actions.append(confirm);
      } else if (execution?.status === "submitted") {
        actions.append(text("span", "已使用批准材料投递", "material-state"));
      } else if (execution?.status === "waiting_for_human") {
        actions.append(text("span", "等待人工处理后继续", "material-state"));
      } else if (!["queued", "preparing_resume", "submitting"].includes(execution?.status)) {
        const prepare = text("button", "使用已批准材料准备申请", "primary");
        prepare.type = "button";
        prepare.addEventListener("click", () => prepareApproved(job, prepare));
        actions.append(prepare);
      } else {
        actions.append(text("span", "申请任务处理中，请手动刷新查看状态", "material-state"));
      }
    }
    if (approved && job.apply_type === "apply") {
      const coverOnly = job.material.material_mode === "cover_letter_only";
      const handoff = text(
        "button",
        coverOnly
          ? "使用默认简历和求职信人工投递"
          : "下载定制简历并人工投递",
        "primary",
      );
      handoff.type = "button";
      handoff.addEventListener("click", () => manualHandoff(job, handoff));
      actions.append(handoff);
    }
  } else if (job.selected) {
    actions.append(text("span", "等待生成定制材料", "material-state"));
  }

  checkbox.disabled = job.application_task?.status === "applying";
  return actions;
}

async function prepareApproved(job, button) {
  button.disabled = true;
  setError();
  try {
    const response = await fetch(
      `/api/jobs/${encodeURIComponent(job.job_id)}/applications/prepare`,
      { method: "POST" },
    );
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "无法准备申请。");
    job.approved_application = payload;
    button.replaceWith(text("span", "申请任务已排队，请稍后手动刷新", "material-state"));
    setStatus(`${job.title} 的定制材料申请任务已排队。`);
  } catch (error) {
    button.disabled = false;
    setError(error.message);
  }
}

async function confirmApproved(execution, button) {
  button.disabled = true;
  setError();
  try {
    const response = await fetch(
      `/api/approved-applications/${encodeURIComponent(execution.id)}/confirm`,
      { method: "POST" },
    );
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "无法确认提交。");
    button.replaceWith(text("span", "正在提交，请稍后手动刷新", "material-state"));
    setStatus("已确认提交，Worker 正在执行最终投递。");
  } catch (error) {
    button.disabled = false;
    setError(error.message);
  }
}

async function manualHandoff(job, button) {
  button.disabled = true;
  const jobWindow = window.open("about:blank", "_blank", "noopener");
  setError();
  try {
    const response = await fetch(
      `/api/jobs/${encodeURIComponent(job.job_id)}/applications/manual-handoff`,
      { method: "POST" },
    );
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "无法准备人工投递材料。");
    if (payload.resume_url) {
      const download = document.createElement("a");
      download.href = payload.resume_url;
      download.download = "";
      download.click();
    }
    await navigator.clipboard.writeText(payload.cover_letter_text);
    if (jobWindow) jobWindow.location = payload.job_url;
    setStatus(
      payload.resume_url
        ? "定制简历已下载，求职信已复制，并已打开 JobsDB 职位页。"
        : "将使用 JobsDB 默认简历，求职信已复制，并已打开职位页。",
    );
  } catch (error) {
    if (jobWindow) jobWindow.close();
    setError(error.message);
  } finally {
    button.disabled = false;
  }
}

function renderJob(job) {
  const card = document.createElement("article");
  card.className = "job-card";
  card.dataset.jobId = job.job_id;

  const heading = document.createElement("div");
  heading.className = "job-heading";
  const titleRow = document.createElement("div");
  titleRow.className = "job-title-row";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = job.selected;
  checkbox.setAttribute("aria-label", `选择 ${job.title}`);
  checkbox.addEventListener("change", () => updateSelection(job, checkbox));
  titleRow.append(checkbox);
  const identity = document.createElement("div");
  identity.append(text("h2", job.title));
  identity.append(text("p", `${job.company} · ${job.location || "未注明地点"}`, "muted"));
  titleRow.append(identity);
  heading.append(titleRow);
  const score = job.overall_score === null
    ? "待评分"
    : `${job.overall_score.toFixed(1)} / 5`;
  heading.append(text("div", score, "score"));
  card.append(heading);

  const meta = document.createElement("p");
  meta.className = "job-meta";
  meta.append(text("span", job.apply_type === "quick_apply" ? "快捷投递" : "外部投递", "badge"));
  if (job.selection_status) meta.append(" 等待生成申请材料");
  card.append(meta);

  if (job.dimensions.length) {
    card.append(
      text(
        "p",
        job.dimensions
          .map((item) => `${item.code} ${item.score === null ? "—" : item.score.toFixed(1)}`)
          .join("  ·  "),
        "dimensions",
      ),
    );
  }
  if (job.recommendation) card.append(text("p", `建议：${job.recommendation}`));

  const review = document.createElement("div");
  review.className = "review-columns";
  review.append(listBlock("匹配优势", job.strengths));
  review.append(listBlock("能力缺口", job.gaps));
  review.append(listBlock("求职风险", job.risks));
  card.append(review);
  card.append(renderTrace(job));
  card.append(renderActions(job, checkbox));
  return card;
}

async function updateSelection(job, checkbox) {
  const intended = checkbox.checked;
  checkbox.disabled = true;
  setError();
  try {
    const response = await fetch(`/api/selections/${encodeURIComponent(job.job_id)}`, {
      method: intended ? "PUT" : "DELETE",
    });
    if (!response.ok) throw new Error("无法保存职位选择状态。");
    job.selected = intended;
    job.selection_status = intended ? "waiting_for_materials" : null;
    currentPage.summary.selected += intended ? 1 : -1;
    elements.selectedCount.textContent = currentPage.summary.selected;
    setMaterialButtonsDisabled(currentPage.summary.selected === 0);
    setStatus(`${job.title} 已${intended ? "选择" : "取消选择"}。`);
  } catch (error) {
    checkbox.checked = !intended;
    setError(error.message);
  } finally {
    checkbox.disabled = false;
  }
}

async function pollApplication(taskId, button) {
  for (;;) {
    const response = await fetch(`/api/applications/${encodeURIComponent(taskId)}`);
    if (!response.ok) throw new Error("无法读取投递状态。");
    const task = await response.json();
    if (task.status === "applying") {
      await new Promise((resolve) => setTimeout(resolve, 800));
      continue;
    }
    button.disabled = ["submitted", "skipped_already_applied"].includes(task.status);
    button.textContent = task.status === "submitted" ? "已投递" : "使用默认简历直接投递";
    setStatus(`投递状态：${task.status}。`);
    if (!["submitted", "skipped_already_applied"].includes(task.status)) {
      setError(`投递需要人工处理：${task.error_message || task.status}。`);
    }
    return;
  }
}

async function confirmApplication() {
  if (!pendingApplyJob) return;
  const { job, button } = pendingApplyJob;
  pendingApplyJob = null;
  button.disabled = true;
  button.textContent = "投递中…";
  setError();
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(job.job_id)}/quick-apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        resume_mode: "jobsdb_default",
        cover_letter_mode: "none",
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "无法启动投递。");
    await pollApplication(payload.id, button);
  } catch (error) {
    button.disabled = false;
    button.textContent = "使用默认简历直接投递";
    setError(error.message);
  }
}

async function loadJobs({ preserveContentOnError = false } = {}) {
  setError();
  if (!preserveContentOnError) {
    elements.list.replaceChildren(text("p", "正在加载职位…", "muted"));
  }
  try {
    const response = await fetch(`/api/jobs${queryForApi()}`);
    if (!response.ok) throw new Error("无法加载职位。");
    currentPage = await response.json();
    elements.totalCount.textContent = currentPage.summary.total;
    elements.evaluatedCount.textContent = currentPage.summary.evaluated;
    elements.pendingCount.textContent = currentPage.summary.pending;
    elements.selectedCount.textContent = currentPage.summary.selected;
    setMaterialButtonsDisabled(currentPage.summary.selected === 0);
    const cards = currentPage.jobs.map(renderJob);
    elements.list.replaceChildren(
      ...(cards.length ? cards : [text("p", "没有符合当前筛选条件的职位。", "muted")]),
    );
  } catch (error) {
    if (!preserveContentOnError) elements.list.replaceChildren();
    setError(error.message);
  }
}

async function generateSelectedMaterials(mode, button) {
  const originalLabel = button.textContent;
  setMaterialButtonsDisabled(true);
  button.textContent = "正在创建任务…";
  setError();
  try {
    const response = await fetch("/api/material-batches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ material_mode: mode }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "无法创建材料生成任务。");
    elements.materialBatchStatus.hidden = false;
    elements.materialBatchNote.textContent =
      `批次 ${payload.batch_id}：已创建 ${payload.tasks.length} 个独立职位任务（` +
      `${mode === "cover_letter_only" ? "默认简历 + 定制求职信" : "定制简历 + 求职信"}）。` +
      "请保持当前 CC/Codex Agent 会话运行，完成后手动刷新页面。";
    setStatus(`已创建 ${payload.tasks.length} 个材料生成任务。`);
  } catch (error) {
    setError(error.message);
  } finally {
    setMaterialButtonsDisabled(!currentPage?.summary.selected);
    button.textContent = originalLabel;
  }
}

async function loadEvaluationProgress() {
  try {
    const response = await fetch("/api/evaluation-progress");
    if (!response.ok) throw new Error();
    const progress = await response.json();
    elements.progressTotal.textContent = progress.total;
    elements.progressQueued.textContent = progress.queued;
    elements.progressRunning.textContent = progress.running;
    elements.progressCompleted.textContent = progress.completed;
    elements.progressFailed.textContent = progress.failed;
    if (progress.status === "active") {
      elements.progressStatus.textContent = "评分任务进行中";
      elements.progressNote.textContent = "当前 Agent 会话正在处理本批 Career Ops 真实评分。";
    } else if (progress.status === "completed") {
      elements.progressStatus.textContent = "本批评分已完成";
      elements.progressNote.textContent = "可以在下方查看最新评分结果。";
    } else {
      elements.progressStatus.textContent = "尚未启动";
      elements.progressNote.textContent = "Dashboard 只展示结果，需要当前 Agent 会话执行评分。";
    }
  } catch {
    elements.progressStatus.textContent = "进度暂不可用";
  }
}

const batchStatusLabels = {
  discovering: "正在后台抓取",
  waiting_for_scoring: "抓取完成，等待评分",
  scoring: "评分任务进行中",
  scored: "本批评分已完成",
  ready: "本批已准备好",
  failed: "抓取失败",
};

async function loadBatchStatus() {
  elements.refreshBatchStatus.disabled = true;
  try {
    const response = await fetch("/api/job-batch");
    if (!response.ok) throw new Error("无法读取批次状态");
    const payload = await response.json();
    if (!payload.batch) {
      elements.batchStatus.textContent = "暂无当前批次";
      return;
    }
    const label = batchStatusLabels[payload.batch.status] || payload.batch.status;
    const error = payload.batch.error_message ? `：${payload.batch.error_message}` : "";
    elements.batchStatus.textContent =
      `${payload.batch.keyword} · ${label} · ${payload.job_count} 个职位${error}`;
  } catch (error) {
    elements.batchStatus.textContent = error.message;
  } finally {
    elements.refreshBatchStatus.disabled = false;
  }
}

async function archiveAndDiscover() {
  const keyword = elements.nextBatchKeyword.value.trim();
  if (!keyword) {
    setError("请输入下一批职位的搜索关键词。");
    elements.nextBatchKeyword.focus();
    return;
  }
  elements.archiveAndDiscover.disabled = true;
  setError();
  try {
    const response = await fetch("/api/job-batches/next", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "无法启动下一批抓取");
    await Promise.all([loadJobs(), loadBatchStatus()]);
    setStatus("当前批次已归档，下一批正在后台抓取。");
  } catch (error) {
    setError(error.message);
  } finally {
    elements.archiveAndDiscover.disabled = false;
  }
}

function filtersChanged() {
  updateUrlFromFilters();
  loadJobs();
}

async function refreshDashboard() {
  elements.refreshResults.disabled = true;
  elements.refreshResults.textContent = "刷新中…";
  try {
    await Promise.all([
      loadJobs({ preserveContentOnError: true }),
      loadEvaluationProgress(),
    ]);
    setStatus("评分结果已刷新。");
  } finally {
    elements.refreshResults.disabled = false;
    elements.refreshResults.textContent = "刷新评分结果";
  }
}

[elements.show, elements.score, elements.type, elements.selection].forEach((control) => {
  control.addEventListener("change", filtersChanged);
});
elements.query.addEventListener("input", () => {
  window.clearTimeout(elements.query.delay);
  elements.query.delay = window.setTimeout(filtersChanged, 250);
});
elements.dialog.addEventListener("close", () => {
  if (elements.dialog.returnValue === "confirm") confirmApplication();
  else pendingApplyJob = null;
});
elements.refreshResults.addEventListener("click", refreshDashboard);
elements.refreshBatchStatus.addEventListener("click", async () => {
  await Promise.all([loadBatchStatus(), loadJobs({ preserveContentOnError: true })]);
});
elements.archiveAndDiscover.addEventListener("click", archiveAndDiscover);
elements.generateCoverLetters.addEventListener(
  "click",
  () => generateSelectedMaterials(
    "cover_letter_only",
    elements.generateCoverLetters,
  ),
);
elements.generateFullMaterials.addEventListener(
  "click",
  () => generateSelectedMaterials(
    "tailored_resume_and_cover_letter",
    elements.generateFullMaterials,
  ),
);

filtersFromUrl();
loadJobs();
loadEvaluationProgress();
loadBatchStatus();
