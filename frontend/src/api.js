const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");
//comment
async function safeJson(resp) {
  const text = await resp.text();
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

export async function uploadResume(file) {
  const fd = new FormData();
  fd.append("file", file);

  const resp = await fetch(`${API_BASE}/api/resume`, {
    method: "POST",
    body: fd,
  });

  if (!resp.ok) throw new Error((await resp.text()) || "Upload failed");
  return resp.json(); // { doc_id, filename, text_preview, text_chars }
}

export async function parseResume(docId) {
  const resp = await fetch(`${API_BASE}/api/resume/${docId}/parse`, {
    method: "POST",
  });
  if (!resp.ok) throw new Error((await resp.text()) || "Parse failed");
  return resp.json();
}

export async function chatResume(docId, message) {
  const resp = await fetch(`${API_BASE}/api/resume/${docId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!resp.ok) throw new Error((await resp.text()) || "Chat failed");
  return resp.json();
}

export async function exportResume(docId) {
  const resp = await fetch(`${API_BASE}/api/resume/${docId}/export`, {
    method: "POST",
  });
  const data = await safeJson(resp);
  if (!resp.ok) throw new Error(data?.detail || data?.raw || "Export failed");
  return data; // { download_url, export_key, ... }
}

export async function previewResume(docId) {
  const resp = await fetch(`${API_BASE}/api/resume/${docId}/preview`, {
    method: "POST",
  });
  if (!resp.ok) throw new Error((await resp.text()) || "Preview failed");
  return resp.json();
}

export async function searchJobs({ role, min_salary_usd, limit }) {
  const payload = {
    role,
    min_salary_usd: min_salary_usd ?? null,
    limit: limit ?? 10,
  };

  const resp = await fetch(`${API_BASE}/api/jobs/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await safeJson(resp);
  if (!resp.ok) throw new Error(data?.detail || data?.raw || "Job search failed");
  return data; // JobSearchResponse: { role, results: [...] }
}

export async function tailorResume(docId, jobDescription) {
  const resp = await fetch(`${API_BASE}/api/resume/${docId}/tailor`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_description: jobDescription }),
  });
  if (!resp.ok) throw new Error((await resp.text()) || "Tailor failed");
  return resp.json();
}
