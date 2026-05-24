import { useState, useRef, useEffect, useCallback } from "react";

const API_URL = "http://localhost:8000";

const SUGGESTED = [
  "What's the most critical problem right now?",
  "Which sectors are chronically sick?",
  "Why did the agent choose that action?",
  "Is the farm improving or getting worse?",
  "Which sectors have been treated today?",
  "What anomalies are spreading?",
];

function useStreamingChat() {
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef(null);

  const send = useCallback(async (question) => {
    if (!question.trim() || streaming) return;

    const userMsg = { role: "user", text: question, id: Date.now() };
    const assistantMsg = { role: "assistant", text: "", id: Date.now() + 1, done: false };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantMsg.id ? { ...m, done: true } : m))
            );
            break;
          }
          try {
            const chunk = JSON.parse(payload);
            if (chunk.error) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsg.id
                    ? { ...m, text: `Error: ${chunk.error}`, done: true, error: true }
                    : m
                )
              );
            } else if (chunk.text) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsg.id ? { ...m, text: m.text + chunk.text } : m
                )
              );
            }
          } catch {}
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, text: "Connection error — is the backend running?", done: true, error: true }
              : m
          )
        );
      }
    } finally {
      setStreaming(false);
    }
  }, [streaming]);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
  }, []);

  const clear = useCallback(() => setMessages([]), []);

  return { messages, streaming, send, abort, clear };
}

function Cursor() {
  return <span style={styles.cursor}>▍</span>;
}

export default function ChatPanel() {
  const { messages, streaming, send, abort, clear } = useStreamingChat();
  const [input, setInput] = useState("");
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const q = input.trim();
    if (!q) return;
    setInput("");
    send(q);
  };

  const handleSuggest = (q) => {
    if (streaming) return;
    setInput(q);
    inputRef.current?.focus();
  };

  return (
    <div style={styles.panel}>
      {/* Messages */}
      <div style={styles.messages}>
        {messages.length === 0 && (
          <div style={styles.welcome}>
            <div style={styles.welcomeTitle}>Ask the farm anything</div>
            <div style={styles.welcomeSub}>I have access to live sensor data, agent memory, and decision history.</div>
            <div style={styles.suggestions}>
              {SUGGESTED.map((q) => (
                <button key={q} style={styles.suggestBtn} onClick={() => handleSuggest(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} style={{ ...styles.msg, ...(msg.role === "user" ? styles.userMsg : styles.assistantMsg) }}>
            <div style={{ ...styles.msgRole, color: msg.role === "user" ? "#58a6ff" : "#4caf50" }}>
              {msg.role === "user" ? "YOU" : "NEUROFIELD"}
            </div>
            <div style={{ ...styles.msgText, color: msg.error ? "#f44336" : undefined }}>
              {msg.text || (msg.role === "assistant" && !msg.done ? <Cursor /> : null)}
              {msg.role === "assistant" && !msg.done && msg.text && <Cursor />}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} style={styles.inputRow}>
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about the farm…"
          disabled={streaming}
          style={styles.input}
        />
        {streaming ? (
          <button type="button" onClick={abort} style={{ ...styles.sendBtn, background: "#f44336" }}>
            Stop
          </button>
        ) : (
          <button type="submit" disabled={!input.trim()} style={styles.sendBtn}>
            Send
          </button>
        )}
      </form>

      {messages.length > 0 && !streaming && (
        <button onClick={clear} style={styles.clearBtn}>Clear conversation</button>
      )}
    </div>
  );
}

const styles = {
  panel: {
    display: "flex", flexDirection: "column", height: "100%", gap: 8,
  },
  messages: {
    flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 10,
    paddingRight: 2,
  },
  welcome: { display: "flex", flexDirection: "column", gap: 8, marginTop: 8 },
  welcomeTitle: { fontSize: 13, fontWeight: 700, color: "#4caf50" },
  welcomeSub: { fontSize: 11, color: "#8b949e", lineHeight: 1.5 },
  suggestions: { display: "flex", flexDirection: "column", gap: 4, marginTop: 4 },
  suggestBtn: {
    background: "#21262d", border: "1px solid #30363d", borderRadius: 4,
    color: "#8b949e", fontSize: 10, padding: "5px 8px", cursor: "pointer",
    textAlign: "left", fontFamily: "inherit",
    transition: "border-color 0.15s",
  },
  msg: { display: "flex", flexDirection: "column", gap: 3 },
  userMsg: { alignItems: "flex-end" },
  assistantMsg: { alignItems: "flex-start" },
  msgRole: { fontSize: 9, fontWeight: 700, letterSpacing: 1 },
  msgText: {
    fontSize: 11, lineHeight: 1.6, color: "#c9d1d9",
    background: "#21262d", padding: "6px 10px", borderRadius: 6,
    maxWidth: "95%", whiteSpace: "pre-wrap", wordBreak: "break-word",
  },
  cursor: {
    display: "inline-block", color: "#4caf50",
    animation: "blink 1s step-end infinite",
  },
  inputRow: { display: "flex", gap: 6 },
  input: {
    flex: 1, background: "#21262d", border: "1px solid #30363d",
    borderRadius: 4, color: "#e6edf3", fontSize: 11, padding: "6px 10px",
    fontFamily: "inherit", outline: "none",
  },
  sendBtn: {
    background: "#4caf50", border: "none", borderRadius: 4,
    color: "#fff", fontSize: 11, fontWeight: 600,
    padding: "6px 12px", cursor: "pointer", fontFamily: "inherit",
  },
  clearBtn: {
    background: "none", border: "none", color: "#8b949e",
    fontSize: 10, cursor: "pointer", fontFamily: "inherit",
    textDecoration: "underline", alignSelf: "center",
  },
};
