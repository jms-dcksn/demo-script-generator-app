"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [url, setUrl] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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
    const hasAttachments = files.length > 0 || url.trim();
    let body: FormData | string;
    const headers: Record<string, string> = {};

    if (hasAttachments) {
      const fd = new FormData();
      fd.append("messages", JSON.stringify(history));
      if (url.trim()) fd.append("url", url.trim());
      files.forEach((f) => fd.append("files", f));
      body = fd;
    } else {
      body = JSON.stringify({ messages: history });
      headers["Content-Type"] = "application/json";
    }

    // Clear file state after sending
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";

    // Add placeholder assistant message
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const resp = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers,
        body,
      });

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

      const reader = resp.body.getReader();
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
          if (payload === "[DONE]") break;
          try {
            const parsed = JSON.parse(payload);
            if (parsed.content) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
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

    setLoading(false);
  }, [input, url, files, messages, loading]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h1 style={styles.title}>Demo Script Generator</h1>
        <p style={styles.subtitle}>
          Create structured demo scripts for your products
        </p>
      </header>

      {/* URL input bar */}
      <div style={styles.urlBar}>
        <input
          type="url"
          placeholder="Product website URL (optional)"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          style={styles.urlInput}
        />
      </div>

      {/* Message list */}
      <div style={styles.messageArea}>
        {messages.length === 0 && (
          <div style={styles.emptyState}>
            <p style={styles.emptyTitle}>Start a conversation</p>
            <p style={styles.emptyText}>
              Describe your product and the demo you want to create. You can
              paste a product URL above or attach files below.
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              ...styles.messageBubbleRow,
              justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
            }}
          >
            <div
              style={{
                ...styles.messageBubble,
                ...(msg.role === "user"
                  ? styles.userBubble
                  : styles.assistantBubble),
              }}
            >
              {msg.role === "assistant" ? (
                <div style={styles.markdown}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content || (loading && i === messages.length - 1 ? "..." : "")}
                  </ReactMarkdown>
                </div>
              ) : (
                <p style={styles.messageText}>{msg.content}</p>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* File chips */}
      {files.length > 0 && (
        <div style={styles.fileChips}>
          {files.map((f, i) => (
            <span key={i} style={styles.chip}>
              {f.name}
              <button
                onClick={() => removeFile(i)}
                style={styles.chipRemove}
                aria-label={`Remove ${f.name}`}
              >
                x
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Input area */}
      <div style={styles.inputArea}>
        <button
          onClick={() => fileInputRef.current?.click()}
          style={styles.attachButton}
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
          style={styles.textInput}
        />
        <button
          onClick={sendMessage}
          disabled={loading || (!input.trim() && files.length === 0)}
          style={{
            ...styles.sendButton,
            opacity: loading || (!input.trim() && files.length === 0) ? 0.5 : 1,
          }}
        >
          Send
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    maxWidth: 800,
    margin: "0 auto",
    padding: "0 16px",
  },
  header: {
    textAlign: "center",
    padding: "24px 0 8px",
  },
  title: {
    fontSize: 22,
    fontWeight: 700,
  },
  subtitle: {
    fontSize: 14,
    color: "var(--text-secondary)",
    marginTop: 4,
  },
  urlBar: {
    padding: "8px 0",
  },
  urlInput: {
    width: "100%",
    padding: "10px 14px",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    fontSize: 14,
    outline: "none",
    background: "var(--input-bg)",
  },
  messageArea: {
    flex: 1,
    overflowY: "auto",
    padding: "12px 0",
  },
  emptyState: {
    textAlign: "center",
    marginTop: 80,
    color: "var(--text-secondary)",
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: 600,
    marginBottom: 8,
    color: "var(--text)",
  },
  emptyText: {
    fontSize: 14,
    maxWidth: 400,
    margin: "0 auto",
    lineHeight: 1.5,
  },
  messageBubbleRow: {
    display: "flex",
    marginBottom: 12,
  },
  messageBubble: {
    maxWidth: "80%",
    padding: "10px 16px",
    borderRadius: "var(--radius)",
    fontSize: 15,
    lineHeight: 1.6,
  },
  userBubble: {
    background: "var(--user-bg)",
    color: "var(--user-text)",
  },
  assistantBubble: {
    background: "var(--assistant-bg)",
    color: "var(--assistant-text)",
  },
  messageText: {
    whiteSpace: "pre-wrap",
    margin: 0,
  },
  markdown: {
    lineHeight: 1.6,
  },
  fileChips: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
    padding: "4px 0",
  },
  chip: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    background: "var(--assistant-bg)",
    borderRadius: 8,
    padding: "4px 10px",
    fontSize: 13,
  },
  chipRemove: {
    background: "none",
    border: "none",
    cursor: "pointer",
    fontSize: 13,
    color: "var(--text-secondary)",
    padding: 0,
  },
  inputArea: {
    display: "flex",
    alignItems: "flex-end",
    gap: 8,
    padding: "12px 0 24px",
    borderTop: "1px solid var(--border)",
  },
  attachButton: {
    width: 40,
    height: 40,
    borderRadius: "50%",
    border: "1px solid var(--border)",
    background: "var(--surface)",
    fontSize: 20,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  textInput: {
    flex: 1,
    padding: "10px 14px",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    fontSize: 15,
    outline: "none",
    resize: "none",
    fontFamily: "inherit",
    lineHeight: 1.5,
    background: "var(--input-bg)",
  },
  sendButton: {
    padding: "10px 20px",
    borderRadius: "var(--radius)",
    border: "none",
    background: "var(--accent)",
    color: "#ffffff",
    fontSize: 15,
    fontWeight: 600,
    cursor: "pointer",
    flexShrink: 0,
  },
};
