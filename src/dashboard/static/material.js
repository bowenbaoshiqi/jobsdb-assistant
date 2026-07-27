const packageId = document.body.dataset.packageId;
const elements = {
  title: document.querySelector("#material-title"),
  meta: document.querySelector("#material-meta"),
  status: document.querySelector("#review-status"),
  error: document.querySelector("#material-error"),
  message: document.querySelector("#material-message"),
  resume: document.querySelector("#resume-preview"),
  download: document.querySelector("#resume-download"),
  cover: document.querySelector("#cover-letter-preview"),
  count: document.querySelector("#cover-letter-count"),
  copy: document.querySelector("#copy-cover-letter"),
  reviewer: document.querySelector("#reviewer-findings"),
  ats: document.querySelector("#ats-findings"),
  facts: document.querySelector("#facts-check-findings"),
  warning: document.querySelector("#fact-warning"),
  factFindings: document.querySelector("#fact-findings"),
  overrideRow: document.querySelector("#fact-override-row"),
  override: document.querySelector("#fact-override"),
  feedback: document.querySelector("#review-feedback"),
  approve: document.querySelector("#approve-material"),
  reject: document.querySelector("#reject-material"),
  regenerate: document.querySelector("#regenerate-material"),
  versions: document.querySelector("#version-history"),
};

let material = null;

function fillList(node, values, emptyText = "没有发现问题") {
  node.replaceChildren();
  (values.length ? values : [emptyText]).forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    node.append(item);
  });
}

function setError(message = "") {
  elements.error.textContent = message;
  elements.error.hidden = !message;
}

function render(payload) {
  material = payload;
  elements.title.textContent = `职位 ${payload.job_id} · 材料 v${payload.version}`;
  elements.meta.textContent =
    `画像 v${payload.profile_version} · 评分记录 ${payload.evaluation_id}`;
  elements.status.textContent = payload.review_status;
  const pdfUrl = `/api/materials/${encodeURIComponent(packageId)}/pdf`;
  elements.resume.src = pdfUrl;
  elements.download.href = pdfUrl;
  elements.cover.textContent = payload.cover_letter_text;
  elements.count.textContent = `${payload.cover_letter_word_count} 个英文单词`;
  fillList(elements.reviewer, payload.reviewer.findings);
  fillList(elements.ats, payload.ats.findings);
  fillList(elements.facts, payload.facts.findings);
  const hasWarning = !payload.facts.passed || payload.facts.findings.length > 0;
  elements.warning.hidden = !hasWarning;
  elements.overrideRow.hidden = !hasWarning;
  fillList(elements.factFindings, payload.facts.findings, "事实检查未通过");
  elements.versions.replaceChildren();
  (payload.versions.length ? payload.versions : [{
    id: payload.id,
    version: payload.version,
    review_status: payload.review_status,
  }]).forEach((version) => {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = `/materials/${encodeURIComponent(version.id)}`;
    link.textContent = `v${version.version} · ${version.review_status}`;
    item.append(link);
    elements.versions.append(item);
  });
}

async function loadMaterial() {
  setError();
  try {
    const response = await fetch(`/api/materials/${encodeURIComponent(packageId)}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "无法读取材料。");
    render(payload);
  } catch (error) {
    setError(error.message);
  }
}

async function review(action) {
  setError();
  const body = action === "approve"
    ? { fact_warning_overridden: elements.override.checked }
    : { feedback: elements.feedback.value.trim() || null };
  try {
    const response = await fetch(
      `/api/materials/${encodeURIComponent(packageId)}/${action}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "无法保存审核结果。");
    if (action === "regenerate") {
      elements.message.textContent =
        `已创建 v${payload.material_version} 重新生成任务，请保持 Agent 会话运行。`;
    } else {
      elements.message.textContent = `审核结果已保存：${payload.resulting_status}`;
      elements.status.textContent = payload.resulting_status;
    }
  } catch (error) {
    setError(error.message);
  }
}

elements.copy.addEventListener("click", async () => {
  if (!material) return;
  await navigator.clipboard.writeText(material.cover_letter_text);
  elements.message.textContent = "求职信已复制。";
});
elements.approve.addEventListener("click", () => review("approve"));
elements.reject.addEventListener("click", () => review("reject"));
elements.regenerate.addEventListener("click", () => review("regenerate"));

loadMaterial();
