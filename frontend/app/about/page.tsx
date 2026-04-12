import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "How This Was Built | Demo Script Generator",
  description: "Architecture and design decisions behind the Demo Script Generator",
};

export default function About() {
  return (
    <div className="about-container">
      <a href="/" className="about-back">
        &larr; Back to app
      </a>

      <h1>How This Was Built</h1>
      <p className="about-subtitle">
        A look at the architecture, tech choices, and design thinking behind the
        Demo Script Generator.
      </p>

      <h2>What It Does</h2>
      <p>
        This tool helps sales engineers and pre-sales professionals create
        structured demo scripts for their products. You provide product context
        -- a website URL, uploaded files, or a description -- and the LLM
        generates a script following proven demo frameworks: limbic openings, the
        3 Key Ideas structure, and Tell-Show-Tell delivery.
      </p>

      <h2>Architecture</h2>
      <div className="about-tech-grid">
        <div className="about-tech-card">
          <div className="tech-label">Frontend</div>
          <div className="tech-value">Next.js 15 + React 19</div>
          <div className="tech-detail">
            App Router, TypeScript, streaming SSE rendering
          </div>
        </div>
        <div className="about-tech-card">
          <div className="tech-label">Backend</div>
          <div className="tech-value">Python FastAPI</div>
          <div className="tech-detail">
            SSE streaming, LangGraph agent orchestration
          </div>
        </div>
        <div className="about-tech-card">
          <div className="tech-label">AI Layer</div>
          <div className="tech-value">LangGraph + OpenAI + Anthropic</div>
          <div className="tech-detail">
            Multi-model agent with human-in-the-loop approval
          </div>
        </div>
        <div className="about-tech-card">
          <div className="tech-label">Infrastructure</div>
          <div className="tech-value">Docker Compose</div>
          <div className="tech-detail">
            Two-service stack, zero-database, stateless deployment
          </div>
        </div>
      </div>

      <h2>The Agent Architecture</h2>
      <p>
        There are actually two LLMs at work here, not one -- and they&apos;re
        from different providers. The orchestrator agent runs on OpenAI&apos;s
        GPT-4.1-mini: fast, cheap, and good enough for routing decisions,
        asking discovery questions, and calling tools. When it has enough
        context, it calls a tool called <code>write_script</code>, which hands
        off to Claude Sonnet -- Anthropic&apos;s model -- with its own system
        prompt specialized purely for script writing.
      </p>
      <p>
        Why two models from two providers? Each model is matched to its job.
        The orchestrator does structured reasoning: parse context, decide what
        to ask next, decide when to search, decide when to write. 4.1-mini
        handles that well and keeps costs low. The script writer is the
        deliverable -- it needs to follow a framework (Tell-Show-Tell, limbic
        opening) while producing natural, compelling prose. Claude is measurably
        better at that kind of structured creative writing.
      </p>
      <p>
        Context window isolation matters too. The script writer gets a clean,
        focused prompt with just the structured context it needs -- no
        conversation history, no back-and-forth noise. It produces a better
        script because it isn&apos;t distracted by twelve messages of discovery
        chat.
      </p>

      {/* Agent flow diagram */}
      <div className="agent-diagram">
        <svg viewBox="0 0 500 420" xmlns="http://www.w3.org/2000/svg">
          {/* Arrow markers */}
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <path d="M0,0 L8,3 L0,6" fill="none" stroke="#4b5069" strokeWidth="1" />
            </marker>
            <marker id="arrow-purple" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <path d="M0,0 L8,3 L0,6" fill="none" stroke="#a78bfa" strokeWidth="1" />
            </marker>
          </defs>

          {/* User node */}
          <rect x="180" y="10" width="140" height="44" rx="22" fill="#6366f1" />
          <text x="250" y="37" textAnchor="middle" fill="#fff" fontSize="13" fontWeight="600">User</text>

          {/* Arrow: User -> Orchestrator */}
          <line x1="250" y1="54" x2="250" y2="82" stroke="#4b5069" strokeWidth="1.5" markerEnd="url(#arrow)" />

          {/* Orchestrator node */}
          <rect x="120" y="82" width="260" height="56" rx="10" fill="#1a1e2e" stroke="#818cf8" strokeWidth="1.5" />
          <text x="250" y="105" textAnchor="middle" fill="#e2e4ea" fontSize="13" fontWeight="600">Orchestrator Agent</text>
          <text x="250" y="123" textAnchor="middle" fill="#8b8fa3" fontSize="11">GPT-4.1-mini (OpenAI)</text>

          {/* Arrow: Orchestrator -> Middleware */}
          <line x1="250" y1="138" x2="250" y2="166" stroke="#4b5069" strokeWidth="1.5" markerEnd="url(#arrow)" />

          {/* Middleware band */}
          <rect x="60" y="166" width="380" height="42" rx="8" fill="#161922" stroke="#252a37" strokeWidth="1" strokeDasharray="4 3" />
          <text x="250" y="185" textAnchor="middle" fill="#6b7185" fontSize="10" fontWeight="500" letterSpacing="0.5">MIDDLEWARE</text>
          <text x="250" y="200" textAnchor="middle" fill="#4b5069" fontSize="9">Human-in-the-Loop | Tool Limit (3) | Model Limit (12)</text>

          {/* Arrows from middleware to tools */}
          <line x1="175" y1="208" x2="120" y2="250" stroke="#4b5069" strokeWidth="1.5" markerEnd="url(#arrow)" />
          <line x1="325" y1="208" x2="380" y2="250" stroke="#4b5069" strokeWidth="1.5" markerEnd="url(#arrow)" />

          {/* Tool: tavily_search */}
          <rect x="40" y="250" width="160" height="48" rx="8" fill="#1a1e2e" stroke="#22d3ee" strokeWidth="1.5" />
          <text x="120" y="273" textAnchor="middle" fill="#22d3ee" fontSize="11" fontWeight="600">tavily_search</text>
          <text x="120" y="287" textAnchor="middle" fill="#6b7185" fontSize="9">Web research</text>

          {/* Tool: write_script */}
          <rect x="300" y="250" width="160" height="48" rx="8" fill="#1a1e2e" stroke="#a78bfa" strokeWidth="1.5" />
          <text x="380" y="273" textAnchor="middle" fill="#a78bfa" fontSize="11" fontWeight="600">write_script</text>
          <text x="380" y="287" textAnchor="middle" fill="#6b7185" fontSize="9">HITL approval gate</text>

          {/* Arrow: write_script -> Script Writer LLM */}
          <line x1="380" y1="298" x2="380" y2="340" stroke="#a78bfa" strokeWidth="1.5" markerEnd="url(#arrow-purple)" />

          {/* Script Writer LLM node */}
          <rect x="260" y="340" width="240" height="56" rx="10" fill="#1a1e2e" stroke="#a78bfa" strokeWidth="1.5" />
          <text x="380" y="363" textAnchor="middle" fill="#e2e4ea" fontSize="13" fontWeight="600">Script Writer LLM</text>
          <text x="380" y="381" textAnchor="middle" fill="#8b8fa3" fontSize="11">Claude Sonnet (Anthropic)</text>
        </svg>
      </div>

      <h2>Middleware as Guardrails</h2>
      <p>
        The agent uses three middleware layers, and each one exists because
        something can go wrong without it:
      </p>
      <p>
        <strong>Human-in-the-loop middleware</strong> intercepts the
        {" "}<code>write_script</code> tool call before it executes. You see what
        the agent is about to generate and can approve, edit the parameters, or
        reject with feedback. This isn&apos;t just a nice UX touch -- it means
        the expensive script generation LLM call only happens when you actually
        want it to.
      </p>
      <p>
        <strong>Tool call limit middleware</strong> caps{" "}
        <code>write_script</code> at 3 calls per session. Without this, a
        confused agent could enter a revision loop -- writing, deciding it&apos;s
        not good enough, rewriting, repeat. Three is enough for an initial
        draft plus a couple of refinements.
      </p>
      <p>
        <strong>Model call limit middleware</strong> is the bluntest instrument:
        12 LLM calls per thread, then the agent wraps up. I&apos;m funding this
        as a free demo, so runaway conversations would be a problem. This is
        the safety net that keeps my API bills from surprises.
      </p>

      <h2>Why SSE Over WebSockets</h2>
      <p>
        The data flow during generation is one-directional -- server streams
        tokens to the client. SSE handles that natively over standard HTTP,
        reconnects automatically, and doesn&apos;t fight proxies or load
        balancers. WebSockets would add complexity for no benefit here.
      </p>

      <h2>Why a Separate Python Backend</h2>
      <p>
        LangChain and LangGraph are Python-first. I could have squeezed the
        agent logic into Next.js API routes, but I&apos;d be fighting the
        ecosystem instead of using it. Python handles orchestration; Next.js
        handles the UI. They talk over REST + SSE. Simple.
      </p>

      <h2>Other Design Choices</h2>
      <p>
        No auth, no database, no user accounts. This is a demo tool -- it
        should be frictionless. Rate limiting is IP-based to keep it fair
        without requiring signups. The discovery agent can run Tavily web
        searches on its own to research your product and industry, so you
        don&apos;t have to spoon-feed it everything.
      </p>

      <div className="about-author">
        <h2>About the Author</h2>
        <p>
          I&apos;m James Dickson, a Principal AI Architect focused on agentic AI and
          enterprise automation. I built this to demonstrate how LLM-powered
          tools can support real pre-sales workflows -- not just chatbots, but
          structured, domain-specific assistants.
        </p>
        <p>
          <a href="https://www.linkedin.com/in/jamescdickson/" target="_blank" rel="noopener noreferrer">
            LinkedIn
          </a>
        </p>
      </div>
    </div>
  );
}
