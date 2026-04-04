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
          <div className="tech-value">LangGraph + OpenAI</div>
          <div className="tech-detail">
            Stateful agent with human-in-the-loop approval
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
        There are actually two LLMs at work here, not one. The agent you chat
        with handles discovery -- asking questions, running web searches, figuring
        out your product and audience. When it has enough context, it calls a
        tool called <code>write_script</code>, which spins up a separate LLM call
        with its own system prompt specialized purely for script writing.
      </p>
      <p>
        Why bother? Context window isolation. The script writer gets a clean,
        focused prompt with just the structured context it needs -- no
        conversation history, no back-and-forth noise. It produces a better
        script because it isn&apos;t distracted by twelve messages of discovery
        chat. The parent agent then reviews the output and presents it to you.
      </p>

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
        the safety net that keeps my OpenAI bill from surprises.
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
