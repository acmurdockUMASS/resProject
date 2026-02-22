import { useMemo, useRef, useState } from "react";
import {
  uploadResume,
  parseResume,
  chatResume,
  exportResume,
  searchJobs,
} from "./api.js";

function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

const AFFIRM_HINTS = ["yes", "yep", "okay", "go ahead", "confirm"];

export default function App() {
  const fileInputRef = useRef(null);

  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  const [docId, setDocId] = useState(null);
  const [filename, setFilename] = useState(null);

  const [messages, setMessages] = useState([
    {
      role: "taylor",
      content:
        "Hi! I’m Taylor ✂️ Upload your resume (PDF/DOCX), then tell me what you want changed.",
    },
  ]);
  const [chatInput, setChatInput] = useState("");

  // Job search prefs
  const [roleQuery, setRoleQuery] = useState("");
  const [minSalary, setMinSalary] = useState(null); // number|null
  const [jobLimit, setJobLimit] = useState(10);

  // Job results
  const [jobResults, setJobResults] = useState([]);
  const [jobError, setJobError] = useState("");

  const gradient = useMemo(
    () =>
      "bg-gradient-to-br from-indigo-500/15 via-fuchsia-500/10 to-sky-500/15",
    []
  );

  async function handleUpload(file) {
    setBusy(true);
    setStatus("Uploading…");
    setJobError("");
    try {
      const up = await uploadResume(file);
      setDocId(up.doc_id);
      setFilename(up.filename);

      setStatus("Parsing…");
      await parseResume(up.doc_id);

      setStatus("Ready ✓");
      setMessages((m) => [
        ...m,
        {
          role: "taylor",
          content:
            "Uploaded + parsed ✓ What do you want to change? (bullets, ordering, tone, skills, etc.)",
        },
      ]);
    } catch (e) {
      setStatus(`Upload/parse failed: ${String(e.message || e)}`);
    } finally {
      setBusy(false);
      window.setTimeout(() => setStatus(""), 2500);
    }
  }

  function onPickFile(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    handleUpload(f);
  }

  function onDrop(e) {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (!f) return;
    handleUpload(f);
  }

  async function sendChat() {
    const text = chatInput.trim();
    if (!text) return;

    setChatInput("");
    setMessages((m) => [...m, { role: "you", content: text }]);

    if (!docId) {
      setMessages((m) => [
        ...m,
        { role: "taylor", content: "Upload your resume first and I’ll be ready." },
      ]);
      return;
    }

    setBusy(true);
    setStatus("Taylor is thinking…");
    try {
      const data = await chatResume(docId, text);

      // Your API returns assistant_message + edits_summary + needs_confirmation + status
      const assistantMessage =
        data.assistant_message ||
        "I can propose edits. Say “yes” to apply or tell me what to adjust.";

      setMessages((m) => [...m, { role: "taylor", content: assistantMessage }]);

      // Nice hint if it’s pending confirmation
      if (data.needs_confirmation) {
        setMessages((m) => [
          ...m,
          {
            role: "taylor",
            content:
              "If you want me to apply those edits, reply with: “yes” (or “go ahead”).",
          },
        ]);
      }

      setStatus("");
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "taylor", content: `Chat failed: ${String(e.message || e)}` },
      ]);
    } finally {
      setBusy(false);
      window.setTimeout(() => setStatus(""), 1500);
    }
  }

  async function handleExport() {
    if (!docId) return;
    setBusy(true);
    setStatus("Exporting…");
    try {
      const data = await exportResume(docId);
      const url = data.download_url;
      if (url) window.open(url, "_blank", "noopener,noreferrer");
      setStatus("Export ready ✓");
    } catch (e) {
      setStatus(`Export failed: ${String(e.message || e)}`);
    } finally {
      setBusy(false);
      window.setTimeout(() => setStatus(""), 2500);
    }
  }

  async function handleJobSearch() {
    setJobError("");
    setBusy(true);
    setStatus("Searching jobs…");
    try {
      const data = await searchJobs({
        role: roleQuery,
        min_salary_usd: minSalary,
        limit: jobLimit,
      });
      setJobResults(data.results || []);
      setStatus(`Found ${(data.results || []).length} jobs ✓`);
    } catch (e) {
      setJobError(String(e.message || e));
      setJobResults([]);
      setStatus("Job search failed");
    } finally {
      setBusy(false);
      window.setTimeout(() => setStatus(""), 2500);
    }
  }

  return (
    <div className={cx("min-h-screen text-slate-900", gradient)}>
      {/* subtle grid */}
      <div className="pointer-events-none fixed inset-0 opacity-40 [background-image:radial-gradient(#ffffff55_1px,transparent_1px)] [background-size:24px_24px]" />

      <div className="relative mx-auto max-w-6xl px-5 py-10">
        {/* Header */}
        <header className="mb-8 flex flex-col gap-2">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-2xl bg-gradient-to-br from-indigo-600 to-fuchsia-600 shadow-sm" />
              <div>
                <div className="text-xl font-semibold tracking-tight">
                  Seamstress
                </div>
                <div className="text-sm text-slate-600">
                  Tailor resumes to fit jobs ✨
                </div>
              </div>
            </div>

            <div className="text-xs text-slate-600">
              {status ? (
                <span className="rounded-full bg-white/70 px-3 py-1 shadow-sm">
                  {status}
                </span>
              ) : (
                <span className="rounded-full bg-white/50 px-3 py-1">
                  live backend ✅
                </span>
              )}
            </div>
          </div>

          <div className="rounded-3xl bg-white/70 p-5 shadow-sm ring-1 ring-white/50">
            <p className="text-lg font-medium leading-snug">
              “Like a seamstress alters clothing to fit perfectly, we alter resumes
              to fit jobs perfectly.”
            </p>
            <p className="mt-2 text-sm text-slate-600">
              Upload a resume, chat with Taylor, export a LaTeX zip, and discover job matches.
            </p>
          </div>
        </header>

        {/* Main grid */}
        <main className="grid gap-5 md:grid-cols-2">
          {/* Left */}
          <section className="rounded-3xl bg-white/70 p-5 shadow-sm ring-1 ring-white/50">
            {/* Upload */}
            <div className="mb-5">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-800">
                  Resume
                </h2>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="rounded-xl bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:opacity-90 disabled:opacity-60"
                    disabled={busy}
                    type="button"
                  >
                    Choose file
                  </button>

                  <button
                    onClick={handleExport}
                    className="rounded-xl bg-gradient-to-br from-indigo-600 to-fuchsia-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:opacity-95 disabled:opacity-60"
                    disabled={busy || !docId}
                    type="button"
                    title={!docId ? "Upload + parse a resume first" : "Export zip"}
                  >
                    Export zip
                  </button>
                </div>

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.docx"
                  onChange={onPickFile}
                  className="hidden"
                />
              </div>

              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={onDrop}
                className={cx(
                  "rounded-2xl border border-dashed p-4 transition",
                  "border-slate-300 bg-white/60",
                  "hover:bg-white/80"
                )}
              >
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 h-9 w-9 rounded-2xl bg-gradient-to-br from-sky-500 to-indigo-600" />
                  <div className="flex-1">
                    <div className="text-sm font-semibold">
                      Drop a PDF or DOCX here
                    </div>
                    <div className="text-xs text-slate-600">
                      We upload → extract text → parse → then Taylor can edit.
                    </div>

                    {filename && (
                      <div className="mt-2 text-xs text-slate-700">
                        <span className="font-semibold">File:</span>{" "}
                        {filename}
                      </div>
                    )}
                    {docId && (
                      <div className="mt-1 text-[11px] text-slate-500">
                        doc id: <span className="font-mono">{docId}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Chat */}
            <div className="flex h-[420px] flex-col rounded-2xl bg-white/60 ring-1 ring-white/60">
              <div className="flex items-center justify-between border-b border-white/60 px-4 py-3">
                <div>
                  <div className="text-sm font-semibold">Taylor ✂️</div>
                  <div className="text-xs text-slate-600">
                    Your resume seamstress
                  </div>
                </div>
                <span className="text-xs text-slate-500">
                  {busy ? "working…" : docId ? "ready" : "upload first"}
                </span>
              </div>

              <div className="flex-1 space-y-3 overflow-auto px-4 py-4">
                {messages.map((m, idx) => (
                  <div
                    key={idx}
                    className={cx(
                      "max-w-[88%] rounded-2xl px-3 py-2 text-sm shadow-sm",
                      m.role === "you"
                        ? "ml-auto bg-slate-900 text-white"
                        : "bg-white text-slate-900"
                    )}
                  >
                    <div className="text-[11px] opacity-70">
                      {m.role === "you" ? "You" : "Taylor"}
                    </div>
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  </div>
                ))}
              </div>

              <div className="border-t border-white/60 p-3">
                <div className="flex gap-2">
                  <input
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") sendChat();
                    }}
                    placeholder='Try: "Make bullets more technical" or reply "yes" to apply edits'
                    className="w-full rounded-xl bg-white px-3 py-2 text-sm outline-none ring-1 ring-white/70 focus:ring-2 focus:ring-indigo-400 disabled:opacity-60"
                    disabled={busy}
                  />
                  <button
                    onClick={sendChat}
                    className="rounded-xl bg-gradient-to-br from-indigo-600 to-fuchsia-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:opacity-95 disabled:opacity-60"
                    disabled={busy}
                    type="button"
                  >
                    Send
                  </button>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {AFFIRM_HINTS.map((w) => (
                    <button
                      key={w}
                      type="button"
                      className="rounded-full bg-white/70 px-3 py-1 text-[11px] text-slate-700 ring-1 ring-white/70 hover:bg-white"
                      onClick={() => setChatInput(w)}
                    >
                      {w}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* Right */}
          <section className="rounded-3xl bg-white/70 p-5 shadow-sm ring-1 ring-white/50">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-800">
                Job Matches
              </h2>
              <span className="rounded-full bg-white/70 px-3 py-1 text-xs text-slate-600 shadow-sm">
                TheirStack
              </span>
            </div>

            {/* Preferences */}
            <div className="mb-4 rounded-2xl bg-white/70 p-4 shadow-sm ring-1 ring-white/70">
              <div className="text-sm font-semibold">Search</div>
              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                <div>
                  <div className="text-[11px] font-semibold text-slate-600">Role / title</div>
                  <input
                    value={roleQuery}
                    onChange={(e) => setRoleQuery(e.target.value)}
                    placeholder="e.g., Software Engineering Intern"
                    className="mt-1 w-full rounded-xl bg-white px-3 py-2 text-sm outline-none ring-1 ring-white/70 focus:ring-2 focus:ring-indigo-400"
                  />
                </div>

                <div>
                  <div className="text-[11px] font-semibold text-slate-600">Min salary (USD) — optional</div>
                  <input
                    type="number"
                    inputMode="numeric"
                    value={minSalary ?? ""}
                    onChange={(e) => {
                      const v = e.target.value.trim();
                      setMinSalary(v === "" ? null : Number(v));
                    }}
                    placeholder="e.g., 90000"
                    className="mt-1 w-full rounded-xl bg-white px-3 py-2 text-sm outline-none ring-1 ring-white/70 focus:ring-2 focus:ring-indigo-400"
                  />
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                {[
                  { label: "No min", value: null },
                  { label: "$60k", value: 60000 },
                  { label: "$80k", value: 80000 },
                  { label: "$100k", value: 100000 },
                  { label: "$120k", value: 120000 },
                ].map((b) => (
                  <button
                    key={b.label}
                    type="button"
                    onClick={() => setMinSalary(b.value)}
                    className={`rounded-xl px-3 py-2 text-xs font-semibold shadow-sm ring-1 ring-white/70 ${
                      minSalary === b.value
                        ? "bg-gradient-to-br from-indigo-600 to-fuchsia-600 text-white"
                        : "bg-white/80 text-slate-800 hover:bg-white"
                    }`}
                  >
                    {b.label}
                  </button>
                ))}

                <div className="ml-auto flex items-center gap-2">
                  <select
                    value={jobLimit}
                    onChange={(e) => setJobLimit(Number(e.target.value))}
                    className="rounded-xl bg-white px-2 py-2 text-xs font-semibold ring-1 ring-white/70"
                  >
                    {[5, 10, 15, 20].map((n) => (
                      <option key={n} value={n}>
                        {n} results
                      </option>
                    ))}
                  </select>

                  <button
                    type="button"
                    onClick={handleJobSearch}
                    disabled={busy || !roleQuery.trim()}
                    className="rounded-xl bg-slate-900 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:opacity-90 disabled:opacity-60"
                    title={!roleQuery.trim() ? "Enter a role/title first" : "Search jobs"}
                  >
                    Find matches
                  </button>
                </div>
              </div>

              {jobError && (
                <div className="mt-3 rounded-xl bg-white/80 p-3 text-xs text-rose-700 ring-1 ring-white/70">
                  {jobError}
                </div>
              )}
            </div>

            {/* Results */}
            <div className="space-y-3">
              {jobResults.length === 0 ? (
                <div className="rounded-2xl bg-white/70 p-4 text-sm text-slate-600 ring-1 ring-white/70">
                  No results yet. Search for a role to populate job matches.
                </div>
              ) : (
                jobResults.map((j) => (
                  <div
                    key={j.job_id || `${j.company}-${j.job_title}`}
                    className="rounded-2xl bg-white/70 p-4 shadow-sm ring-1 ring-white/70"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold">{j.job_title}</div>
                        <div className="text-xs text-slate-600">
                          {j.company}
                          {j.location ? ` • ${j.location}` : ""}
                        </div>
                      </div>

                      {j.salary != null && (
                        <div className="rounded-xl bg-slate-900 px-3 py-1 text-xs font-semibold text-white">
                          ${String(j.salary)}
                        </div>
                      )}
                    </div>

                    <div className="mt-2 flex flex-wrap gap-2">
                      {j.apply_url && (
                        <a
                          href={j.apply_url}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-full bg-slate-900 px-3 py-1 text-[11px] font-semibold text-white hover:opacity-90"
                        >
                          Apply
                        </a>
                      )}
                      {j.date_posted && (
                        <span className="rounded-full bg-white/80 px-3 py-1 text-[11px] text-slate-600 ring-1 ring-white/70">
                          {j.date_posted}
                        </span>
                      )}
                    </div>

                    {j.description && (
                      <p className="mt-2 line-clamp-4 text-xs text-slate-700">
                        {j.description}
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>

            <div className="mt-5 rounded-2xl bg-gradient-to-br from-sky-500/15 to-fuchsia-600/15 p-4 ring-1 ring-white/50">
              <div className="text-sm font-semibold">Next step</div>
              <div className="mt-1 text-xs text-slate-700">
                When your partner finishes “tailor to job,” you’ll add a button on each job:
                <span className="font-semibold"> “Tailor resume to this posting”</span>
                (calls <code className="font-mono">/api/resume/{`{doc_id}`}/tailor</code>).
              </div>
            </div>
          </section>
        </main>

        <footer className="mt-10 text-center text-xs text-slate-600">
          Built for HackHer • Seamstress ✂️
        </footer>
      </div>
    </div>
  );
}