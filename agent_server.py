from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from agents import Agent, Runner
from datetime import datetime
import httpx
import os
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Define Agents ===
manager_agent = Agent(
    name="Manager",
    instructions="""
You are an intelligent router for user requests.
Decide the intent behind the message: strategy, content, repurpose, feedback.
If you are unsure or need more info, ask a clarifying question instead of routing.
Respond in strict JSON like:
{ "route_to": "strategy", "reason": "User wants a campaign plan" }
"""
)

strategy_agent = Agent(
    name="StrategyAgent",
    instructions="""
You create clear, actionable 7-day social media campaign strategies.
If user input is unclear or missing platform, audience, or tone — ask for clarification.
Respond in structured JSON.
"""
)

content_agent = Agent(
    name="ContentAgent",
    instructions="""
You write engaging, brand-aligned social content.
If user input lacks platform or goal, ask for clarification.
Return post drafts with caption, CTA, and hook.
"""
)

repurpose_agent = Agent(
    name="RepurposeAgent",
    instructions="""
You convert existing posts into new formats for different platforms.
If missing input post or target format, ask for clarification.
"""
)

feedback_agent = Agent(
    name="FeedbackAgent",
    instructions="""
You evaluate content and offer improvements.
If missing content or performance data, ask what’s needed.
"""
)

AGENT_MAP = {
    "strategy": strategy_agent,
    "content": content_agent,
    "repurpose": repurpose_agent,
    "feedback": feedback_agent,
}

@app.post("/agent")
async def run_agent(request: Request):
    data = await request.json()
    user_input = data.get("input", "")
    user_id = data.get("user_id", "anonymous")
    linked_profile_strategy = data.get("linked_profile_strategy")
    agent_type = data.get("agent_type")  # Optional shortcut
    webhook_url = data.get("webhook_url")

    # Step 1: If no agent_type, use Manager Agent to decide
    if not agent_type:
        manager_result = await Runner.run(manager_agent, input=user_input)
        try:
            parsed = json.loads(manager_result.final_output)
            agent_type = parsed.get("route_to")
        except:
            return {"needs_clarification": True, "message": "Could not understand intent."}

    agent = AGENT_MAP.get(agent_type)
    if not agent:
        return {"error": f"Unknown agent type: {agent_type}"}

    # Step 2: Run the selected agent
    result = await Runner.run(agent, input=user_input)
    if hasattr(result, "requires_user_input"):
        return {
            "needs_clarification": True,
            "message": result.requires_user_input,
        }

    # Step 3: Format AgentSession
    session = {
        "agent_type": agent_type,
        "user_id": user_id,
        "input_details": data.get("input_details", {}),
        "output_details": result.final_output,
        "linked_profile_strategy": linked_profile_strategy,
        "source_content_piece": data.get("source_content_piece"),
        "created_at": datetime.utcnow().isoformat(),
    }

    # Step 4: Optionally push to external webhook (Make, Bubble, etc)
    if webhook_url:
        async with httpx.AsyncClient() as client:
            try:
                await client.post(webhook_url, json=session)
            except Exception as e:
                session["webhook_error"] = str(e)

    return session
