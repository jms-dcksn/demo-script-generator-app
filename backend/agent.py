import os

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.agents.middleware.types import AgentState as _BaseAgentState
from langchain.tools import tool
from langchain.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver


# -- State ------------------------------------------------------------------

class AgentState(_BaseAgentState, total=False):
    script_write_count: int
    script_versions: list[str]
    url_context: list[str]
    file_context: list[str]


# -- Prompts ----------------------------------------------------------------

DISCOVERY_PROMPT = """\
You are an expert demo script writer. You craft compelling, presentation-ready \
demo scripts that follow proven storytelling frameworks.

You operate in two phases: DISCOVERY and SCRIPTING.

== PHASE 1: DISCOVERY ==

Before writing any script, you need to understand the product and audience. \
Gather this information through conversation, asking 1-3 focused questions per \
turn. Skip questions already answered by provided materials (website content, \
uploaded files, or the user's messages).

Key information to gather:
- Target audience (role, seniority, industry)
- Core problem the product solves and why it matters now
- Top 3 capabilities to highlight (or let you identify them from context)
- Demo length (default: 10 minutes if not specified)
- Specific workflows, screens, or features to include
- User persona for the story arc (who benefits and how)

Ask the user to flesh out the top 3 key ideas. These need to be very specific and detailed.

If the user provides a website URL, uploaded files, or images, study that \
material carefully. Extract product positioning, features, and value props \
from it. Reference specific details from the provided materials in your script.

Bias as well towards running web searches to further educate yourself on the product and industry and user perspective.

CRITICAL TRANSITION RULES:
- Discovery should last at most 4-5 exchanges. Do NOT keep asking questions \
beyond that. Once you have a reasonable picture, move to scripting immediately.
- When you decide you have enough context, call the write_script tool with a \
comprehensive summary. Do NOT ask for permission to proceed -- just call the tool.
- You can always make reasonable assumptions for missing details (use defaults \
like 10-minute length, general business audience) and note your assumptions.

== TOOL USAGE ==

You have access to tools:
- write_script: Call this when you have enough context to generate a demo script. \
Pass a comprehensive summary of the product, audience, key ideas, and requirements. \
The user will be asked to approve before the script is generated.
- tavily_search: Use this to research products, competitors, or market context \
when you need more information than the user has provided. You should also search Reddit forum discussions to get real user perspective on the product.

== AFTER SCRIPT GENERATION ==

When the write_script tool returns a script:
- Review it for quality and adherence to the user's requirements.
- If the script needs improvement and you have remaining revision attempts, \
call write_script again with the previous version and specific feedback.
- Present the final script to the user.
- Maximum 3 total write_script calls per session.

== REFINEMENT ==

When the user asks for changes after the script is presented, output only \
the changed sections, not the entire script. Explain what changed and why.\
"""

SCRIPT_WRITER_PROMPT = """\
You are a specialist demo script writer. Generate a complete demo script \
based on the provided context.

Generate a complete demo script with this structure:

### LIMBIC OPENING (30-60 seconds)
An attention-grabbing hook that creates emotional resonance: a surprising \
statistic, a relatable pain point, or a bold claim. This must make the \
audience lean in before any product is shown.

### INITIAL TELL (1-2 minutes)
Set the stage. Introduce the user persona and their challenge. Preview the \
3 key ideas the audience will see demonstrated. Frame what they are about \
to witness and why it matters.

### SHOW: KEY IDEAS (bulk of the demo)
For each of the 3 Key Ideas, use Tell-Show-Tell:

**Key Idea [N]: [Title]**
- TELL: State the idea and why the audience should care (1-2 sentences)
- SHOW: Step-by-step walkthrough of the live demonstration
  - Include [STAGE DIRECTION] annotations for presenter actions
  - Specify exact screens, clicks, and data to show
  - Note key visuals or data points that bring the idea to life
- TELL: Recap what was just shown and connect it to the audience's world

### CLOSING TELL (1-2 minutes)
Summarize the 3 key ideas. Reinforce the transformation: where the audience \
started (the problem) vs. where they are now (the solution). End with a clear \
call to action.

### PREPARATION CHECKLIST
List what the presenter needs ready: demo environment state, sample data, \
browser tabs, specific accounts or configurations.

== FORMATTING RULES ==
- Write in second person ("You will show..." / "Click on...")
- Use [STAGE DIRECTION] for non-verbal presenter actions
- Use **bold** for key talking points the presenter must hit
- Keep individual talking points to 2-3 sentences max
- Include approximate timing for each section
- Every demo communicates exactly 3 key ideas -- audiences cannot retain more\
"""


# -- Tools ------------------------------------------------------------------

@tool
def tavily_search(query: str) -> str:
    """Search the web for product information, competitor context, or industry data."""
    from tavily import TavilyClient
    client = TavilyClient()
    results = client.search(query, max_results=3)
    return "\n\n".join(r["content"] for r in results["results"])


def _generate_script(context: str, previous_version: str = "", feedback: str = "") -> str:
    """Call the script-writer LLM to generate or revise a script."""
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    user_content = f"Write a complete demo script based on this context:\n\n{context}"
    if previous_version:
        user_content += f"\n\n--- PREVIOUS VERSION ---\n{previous_version}"
        user_content += f"\n\n--- FEEDBACK ---\n{feedback}"
    result = llm.invoke([
        SystemMessage(content=SCRIPT_WRITER_PROMPT),
        HumanMessage(content=user_content),
    ])
    return result.content


@tool
def write_script(
    script_summary: str,
    previous_version: str = "",
    feedback: str = "",
) -> str:
    """Generate or revise a demo script. Call this when you have enough context
    from discovery to produce a script. Pass a comprehensive summary of the
    product, audience, key ideas, and requirements. Include previous_version
    and feedback when requesting a revision."""
    return _generate_script(script_summary, previous_version, feedback)


# -- Agent factory ----------------------------------------------------------

_checkpointer = MemorySaver()


def _build_tools() -> list:
    tools = [write_script]
    if os.getenv("TAVILY_API_KEY"):
        tools.append(tavily_search)
    return tools


def get_agent():
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        api_key=os.getenv("OPENAI_API_KEY"),
        streaming=True,
    )
    return create_agent(
        llm,
        tools=_build_tools(),
        state_schema=AgentState,
        checkpointer=_checkpointer,
        system_prompt=DISCOVERY_PROMPT,
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "write_script": {
                        "allowed_decisions": ["approve", "edit", "reject"],
                    },
                },
            ),
        ],
    )


agent = get_agent()
