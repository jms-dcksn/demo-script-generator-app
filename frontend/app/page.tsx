"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ActionRequest {
  name: string;
  args: Record<string, string>;
  description: string;
}

interface InterruptPayload {
  action_requests: ActionRequest[];
  review_configs: { action_name: string; allowed_decisions: string[] }[];
}

interface ContextItem {
  type: "url" | "file";
  name: string;
  addedAt: number;
}

const SCRIPT_MARKERS = [
  /limbic opening/i,
  /key idea/i,
  /tell[- ]show[- ]tell/i,
  /## (Tell|Show|Opening|Closing|Demo Flow)/i,
];

function isScriptReady(content: string): boolean {
  if (content.length <= 500) return false;
  return SCRIPT_MARKERS.some((re) => re.test(content));
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [urls, setUrls] = useState<string[]>([""]);
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [rateLimited, setRateLimited] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [pendingInterrupt, setPendingInterrupt] = useState<InterruptPayload | null>(null);
  const [editingArgs, setEditingArgs] = useState<Record<string, string> | null>(null);
  const [attachedContext, setAttachedContext] = useState<ContextItem[]>([]);
  const [contextCollapsed, setContextCollapsed] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Fetch usage on mount
  useEffect(() => {
    fetch(`${API_URL}/api/usage`)
      .then((r) => r.json())
      .then((data) => {
        setRemaining(data.remaining);
        if (data.remaining <= 0) setRateLimited(true);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const readStream = useCallback(
    async (resp: Response) => {
      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const payload = line.slice(5).trim();
          if (payload === "[DONE]") return;
          try {
            const parsed = JSON.parse(payload);
            // Track thread_id from backend
            if (parsed.thread_id && !parsed.interrupt) {
              setThreadId(parsed.thread_id);
              continue;
            }
            // Handle interrupt
            if (parsed.interrupt) {
              if (parsed.thread_id) setThreadId(parsed.thread_id);
              setPendingInterrupt(parsed.interrupt);
              setLoading(false);
              return;
            }
            if (parsed.content) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role !== "assistant") return updated;
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + parsed.content,
                };
                return updated;
              });
            }
          } catch {
            // skip malformed lines
          }
        }
      }
    },
    [],
  );

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text && files.length === 0) return;
    if (loading) return;

    const userMessage: Message = { role: "user", content: text };
    const history = [...messages, userMessage];
    setMessages(history);
    setInput("");
    setLoading(true);

    // Build request body
    const nonEmptyUrls = urls.map((u) => u.trim()).filter(Boolean);
    const hasAttachments = files.length > 0 || nonEmptyUrls.length > 0;
    let body: FormData | string;
    const headers: Record<string, string> = {};

    if (hasAttachments) {
      const fd = new FormData();
      fd.append("messages", JSON.stringify(history));
      if (nonEmptyUrls.length > 0)
        fd.append("urls", JSON.stringify(nonEmptyUrls));
      files.forEach((f) => fd.append("files", f));
      if (threadId) fd.append("thread_id", threadId);
      fd.append("is_resume", "false");
      body = fd;
    } else {
      body = JSON.stringify({
        messages: history,
        thread_id: threadId || "",
        is_resume: false,
      });
      headers["Content-Type"] = "application/json";
    }

    // Accumulate context before clearing
    const now = Date.now();
    const newContext: ContextItem[] = [
      ...nonEmptyUrls.map((u) => ({ type: "url" as const, name: u, addedAt: now })),
      ...files.map((f) => ({ type: "file" as const, name: f.name, addedAt: now })),
    ];
    if (newContext.length > 0) {
      setAttachedContext((prev) => [...prev, ...newContext]);
    }

    // Clear attachments after sending
    setUrls([""]);
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";

    // Add placeholder assistant message
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const resp = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers,
        body,
        signal: controller.signal,
      });

      if (resp.status === 429) {
        setRateLimited(true);
        setRemaining(0);
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content:
              "You've reached the free demo limit. Thanks for trying it out!",
          };
          return updated;
        });
        setLoading(false);
        return;
      }

      if (!resp.ok || !resp.body) {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: "Something went wrong. Please try again.",
          };
          return updated;
        });
        setLoading(false);
        return;
      }

      await readStream(resp);
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: "Connection error. Is the backend running?",
        };
        return updated;
      });
    }

    // Refresh usage count
    try {
      const usage = await fetch(`${API_URL}/api/usage`);
      const data = await usage.json();
      setRemaining(data.remaining);
      if (data.remaining <= 0) setRateLimited(true);
    } catch {
      // ignore
    }

    setLoading(false);
  }, [input, urls, files, messages, loading, threadId, readStream]);

  const handleResume = useCallback(
    async (resumePayload: Record<string, unknown>) => {
      if (!pendingInterrupt || !threadId) return;
      setPendingInterrupt(null);
      setEditingArgs(null);
      setLoading(true);

      // Add placeholder assistant message for the response
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      try {
        const resp = await fetch(`${API_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            thread_id: threadId,
            is_resume: true,
            resume_payload: resumePayload,
          }),
        });

        if (!resp.ok || !resp.body) {
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: "assistant",
              content: "Something went wrong resuming. Please try again.",
            };
            return updated;
          });
          setLoading(false);
          return;
        }

        await readStream(resp);
      } catch {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: "Connection error. Is the backend running?",
          };
          return updated;
        });
      }

      // Refresh usage count
      try {
        const usage = await fetch(`${API_URL}/api/usage`);
        const data = await usage.json();
        setRemaining(data.remaining);
        if (data.remaining <= 0) setRateLimited(true);
      } catch {
        // ignore
      }

      setLoading(false);
    },
    [pendingInterrupt, threadId, readStream],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const isLoadingLast = (i: number) =>
    loading && i === messages.length - 1;

  const exportMessage = (content: string) => {
    const blob = new Blob([content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "demo-script.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  const removeContext = (index: number) => {
    setAttachedContext((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className={`app-container ${attachedContext.length > 0 ? "has-context" : ""}`}>
      <header className="app-header">
        <h1 className="app-title">Demo Script Generator</h1>
        <p className="app-subtitle">
          Create structured demo scripts for your products
        </p>
        {remaining !== null && (
          <p className="usage-note">
            {rateLimited
              ? "You've used your free demo. Thanks for trying it out!"
              : `Free demo -- ${remaining} message${remaining === 1 ? "" : "s"} remaining`}
          </p>
        )}
      </header>

      {/* Context panel */}
      {attachedContext.length > 0 && (
        <div className={`context-panel ${contextCollapsed ? "collapsed" : ""}`}>
          <button
            className="context-toggle"
            onClick={() => setContextCollapsed((c) => !c)}
          >
            <span className="context-toggle-label">
              Context ({attachedContext.length} item{attachedContext.length !== 1 ? "s" : ""})
            </span>
            <svg
              className={`context-chevron ${contextCollapsed ? "rotated" : ""}`}
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          {!contextCollapsed && (
            <ul className="context-list">
              {attachedContext.map((item, i) => (
                <li key={i} className="context-item">
                  <svg
                    className="context-item-icon"
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    {item.type === "url" ? (
                      <>
                        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                      </>
                    ) : (
                      <>
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                      </>
                    )}
                  </svg>
                  <span className="context-item-name" title={item.name}>
                    {item.type === "url"
                      ? item.name.replace(/^https?:\/\/(www\.)?/, "").slice(0, 40)
                      : item.name}
                  </span>
                  <button
                    className="context-item-remove"
                    onClick={() => removeContext(i)}
                    aria-label={`Remove ${item.name}`}
                  >
                    x
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* URL input bar */}
      <div className="url-bar">
        {urls.map((u, i) => (
          <div key={i} className="url-row">
            <input
              type="url"
              placeholder="Product website URL (optional)"
              value={u}
              onChange={(e) => {
                const next = [...urls];
                next[i] = e.target.value;
                setUrls(next);
              }}
              className="url-input"
            />
            {i > 0 && (
              <button
                className="url-remove"
                onClick={() => setUrls(urls.filter((_, j) => j !== i))}
                aria-label="Remove URL"
              >
                x
              </button>
            )}
          </div>
        ))}
        <button
          className="url-add"
          onClick={() => setUrls([...urls, ""])}
        >
          + Add another URL
        </button>
      </div>

      {/* Message list */}
      <div className="message-area">
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"
                />
              </svg>
            </div>
            <p className="empty-title">Start a conversation</p>
            <p className="empty-text">
              Describe your product and the demo you want to create. You can
              paste a product URL above or attach files below.
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`message-row ${msg.role}`}
          >
            <div className={`message-bubble ${msg.role}`}>
              {msg.role === "assistant" ? (
                !msg.content && isLoadingLast(i) ? (
                  <div className="loading-dots">
                    <span />
                    <span />
                    <span />
                  </div>
                ) : (
                  <div className="markdown-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                    {isScriptReady(msg.content) && !isLoadingLast(i) && (
                      <button
                        className="export-button"
                        onClick={() => exportMessage(msg.content)}
                        title="Export as .md"
                      >
                        <svg
                          width="14"
                          height="14"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                          <polyline points="7 10 12 15 17 10" />
                          <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                        Export
                      </button>
                    )}
                  </div>
                )
              ) : (
                <p className="message-text">{msg.content}</p>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Interrupt approval bar */}
      {pendingInterrupt && !editingArgs && (() => {
        const req = pendingInterrupt.action_requests[0];
        return (
          <div className="interrupt-bar">
            <p className="interrupt-description">{req.description}</p>
            <p className="interrupt-summary">
              {req.args.script_summary?.slice(0, 200)}
              {(req.args.script_summary?.length ?? 0) > 200 ? "..." : ""}
            </p>
            <div className="interrupt-actions">
              <button
                className="interrupt-btn approve"
                onClick={() =>
                  handleResume({ decisions: [{ type: "approve" }] })
                }
              >
                Approve
              </button>
              <button
                className="interrupt-btn edit"
                onClick={() => setEditingArgs({ ...req.args })}
              >
                Edit
              </button>
              <button
                className="interrupt-btn reject"
                onClick={() => {
                  const feedback = prompt("Feedback for the agent:");
                  if (feedback !== null) {
                    handleResume({
                      decisions: [{ type: "reject", message: feedback }],
                    });
                  }
                }}
              >
                Reject
              </button>
            </div>
          </div>
        );
      })()}

      {/* Edit args form */}
      {editingArgs && pendingInterrupt && (() => {
        const req = pendingInterrupt.action_requests[0];
        return (
          <div className="interrupt-bar">
            <p className="interrupt-description">Edit script parameters:</p>
            <textarea
              className="edit-args-input"
              value={editingArgs.script_summary || ""}
              onChange={(e) =>
                setEditingArgs((prev) => ({
                  ...prev!,
                  script_summary: e.target.value,
                }))
              }
              rows={4}
            />
            <div className="interrupt-actions">
              <button
                className="interrupt-btn approve"
                onClick={() =>
                  handleResume({
                    decisions: [
                      {
                        type: "edit",
                        edited_action: {
                          name: req.name,
                          args: editingArgs,
                        },
                      },
                    ],
                  })
                }
              >
                Submit
              </button>
              <button
                className="interrupt-btn reject"
                onClick={() => setEditingArgs(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        );
      })()}

      {/* File chips */}
      {files.length > 0 && (
        <div className="file-chips">
          {files.map((f, i) => (
            <span key={i} className="chip">
              {f.name}
              <button
                onClick={() => removeFile(i)}
                className="chip-remove"
                aria-label={`Remove ${f.name}`}
              >
                x
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Input area */}
      {!pendingInterrupt && (
        <div className="input-area">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="attach-button"
            title="Attach files"
          >
            +
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*,.pdf,.txt,.md,.doc,.docx,.csv"
            style={{ display: "none" }}
            onChange={(e) => {
              if (e.target.files) {
                setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
              }
            }}
          />
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe your product or demo goals..."
            rows={1}
            className="text-input"
          />
          <button
            onClick={sendMessage}
            disabled={loading || rateLimited || (!input.trim() && files.length === 0)}
            className="send-button"
          >
            Send
          </button>
        </div>
      )}
    </div>
  );
}
