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
};

let currentPage = null;
let pendingApplyJob = null;

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
  details.append(text("summary", "Scoring details"));
  const trace = document.createElement("div");
  trace.className = "trace";

  if (job.evaluation_status === "pending") {
    trace.append(text("p", "This job has no persisted structured evaluation."));
  } else {
    job.dimensions.forEach((dimension) => {
      const block = document.createElement("section");
      block.className = "dimension-block";
      const score = dimension.score === null ? "—" : `${dimension.score.toFixed(1)} / 5`;
      block.append(text("h3", `${dimension.code} · ${dimension.title} · ${score}`));
      block.append(listBlock("Findings", dimension.findings));
      block.append(listBlock("Evidence", dimension.evidence));
      trace.append(block);
    });
  }

  const verdict = text(
    "p",
    "No independent structured Profile-requirement verdict is available. Review the persisted A–F evidence.",
    "muted",
  );
  trace.append(verdict);

  if (job.profile_summary) {
    const profile = document.createElement("section");
    profile.className = "profile-summary";
    profile.append(text("h3", `Profile v${job.profile_summary.profile_version}`));
    profile.append(text("p", `Target roles: ${job.profile_summary.target_roles.join(", ") || "—"}`));
    profile.append(text("p", `Preferences: ${JSON.stringify(job.profile_summary.preferences)}`));
    profile.append(text("p", `Exclusions: ${job.profile_summary.exclusions.join("; ") || "—"}`));
    trace.append(profile);
  }

  if (job.provenance) {
    const provenance = document.createElement("section");
    provenance.className = "provenance";
    provenance.append(text("h3", "Evaluation provenance"));
    provenance.append(text("p", `Evaluation: ${job.provenance.evaluation_id}`));
    provenance.append(text("p", `Profile version: ${job.provenance.profile_version}`));
    provenance.append(text("p", `JD snapshot: ${job.provenance.snapshot_id}`));
    provenance.append(text("p", `Career Ops commit: ${job.provenance.engine_commit || "—"}`));
    provenance.append(text("p", `Prompt: ${job.provenance.prompt_version}`));
    trace.append(provenance);
  }

  const jd = document.createElement("section");
  jd.className = "jd";
  jd.append(text("h3", "Current job description"));
  jd.append(text("pre", job.jd_text));
  trace.append(jd);
  details.append(trace);
  return details;
}

function renderActions(job, checkbox) {
  const actions = document.createElement("div");
  actions.className = "job-actions";

  const open = text("a", "Open JobsDB", "button-link");
  open.href = job.canonical_url;
  open.target = "_blank";
  open.rel = "noopener noreferrer";
  actions.append(open);

  if (job.apply_type === "quick_apply") {
    const direct = text("button", "Direct apply with default CV");
    direct.type = "button";
    direct.disabled = ["applying", "submitted", "skipped_already_applied"].includes(
      job.application_task?.status,
    );
    if (job.application_task?.status === "applying") direct.textContent = "Applying…";
    if (job.application_task?.status === "submitted") direct.textContent = "Submitted";
    direct.addEventListener("click", () => {
      pendingApplyJob = { job, button: direct };
      elements.confirmationJob.textContent = `Direct apply to ${job.title} at ${job.company}?`;
      elements.dialog.showModal();
    });
    actions.append(direct);
  } else {
    const manual = text("a", "Open job and apply manually", "button-link");
    manual.href = job.canonical_url;
    manual.target = "_blank";
    manual.rel = "noopener noreferrer";
    actions.append(manual);
  }

  const future = text("button", "Tailored materials (later version)");
  future.type = "button";
  future.disabled = true;
  actions.append(future);

  checkbox.disabled = job.application_task?.status === "applying";
  return actions;
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
  checkbox.setAttribute("aria-label", `Select ${job.title}`);
  checkbox.addEventListener("change", () => updateSelection(job, checkbox));
  titleRow.append(checkbox);
  const identity = document.createElement("div");
  identity.append(text("h2", job.title));
  identity.append(text("p", `${job.company} · ${job.location || "Location not stated"}`, "muted"));
  titleRow.append(identity);
  heading.append(titleRow);
  const score = job.overall_score === null
    ? "Pending evaluation"
    : `${job.overall_score.toFixed(1)} / 5`;
  heading.append(text("div", score, "score"));
  card.append(heading);

  const meta = document.createElement("p");
  meta.className = "job-meta";
  meta.append(text("span", job.apply_type === "quick_apply" ? "Quick Apply" : "Apply", "badge"));
  if (job.selection_status) meta.append(` ${job.selection_status.replaceAll("_", " ")}`);
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
  if (job.recommendation) card.append(text("p", `Recommendation: ${job.recommendation}`));

  const review = document.createElement("div");
  review.className = "review-columns";
  review.append(listBlock("Strengths", job.strengths));
  review.append(listBlock("Gaps", job.gaps));
  review.append(listBlock("Risks", job.risks));
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
    if (!response.ok) throw new Error("Selection could not be saved.");
    job.selected = intended;
    job.selection_status = intended ? "waiting_for_materials" : null;
    currentPage.summary.selected += intended ? 1 : -1;
    elements.selectedCount.textContent = currentPage.summary.selected;
    setStatus(`${job.title} ${intended ? "selected" : "deselected"}.`);
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
    if (!response.ok) throw new Error("Application status is unavailable.");
    const task = await response.json();
    if (task.status === "applying") {
      await new Promise((resolve) => setTimeout(resolve, 800));
      continue;
    }
    button.disabled = ["submitted", "skipped_already_applied"].includes(task.status);
    button.textContent = task.status === "submitted" ? "Submitted" : "Direct apply with default CV";
    setStatus(`Application status: ${task.status}.`);
    if (!["submitted", "skipped_already_applied"].includes(task.status)) {
      setError(`Application requires attention: ${task.error_message || task.status}.`);
    }
    return;
  }
}

async function confirmApplication() {
  if (!pendingApplyJob) return;
  const { job, button } = pendingApplyJob;
  pendingApplyJob = null;
  button.disabled = true;
  button.textContent = "Applying…";
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
    if (!response.ok) throw new Error(payload.detail || "Application could not start.");
    await pollApplication(payload.id, button);
  } catch (error) {
    button.disabled = false;
    button.textContent = "Direct apply with default CV";
    setError(error.message);
  }
}

async function loadJobs() {
  setError();
  elements.list.replaceChildren(text("p", "Loading jobs…", "muted"));
  try {
    const response = await fetch(`/api/jobs${queryForApi()}`);
    if (!response.ok) throw new Error("Jobs could not be loaded.");
    currentPage = await response.json();
    elements.totalCount.textContent = currentPage.summary.total;
    elements.evaluatedCount.textContent = currentPage.summary.evaluated;
    elements.pendingCount.textContent = currentPage.summary.pending;
    elements.selectedCount.textContent = currentPage.summary.selected;
    const cards = currentPage.jobs.map(renderJob);
    elements.list.replaceChildren(
      ...(cards.length ? cards : [text("p", "No jobs match these filters.", "muted")]),
    );
  } catch (error) {
    elements.list.replaceChildren();
    setError(error.message);
  }
}

function filtersChanged() {
  updateUrlFromFilters();
  loadJobs();
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

filtersFromUrl();
loadJobs();
