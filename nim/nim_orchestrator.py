import os
import requests
import argparse
from typing import Annotated, TypedDict, List
from dotenv import load_dotenv

from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

load_dotenv()

# Configuration
OBSIDIAN_URL = "http://127.0.0.1:27123"
OBSIDIAN_KEY = "9d59473739d28df112a36b4e30b9a193e4cfb76257498302b1bbd58d25cb72dc"
PROJECT_PATH = "Memory/projects/soft-recovery-app"

# 1. Define the State
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], lambda x, y: x + y]
    context: str
    critiques: List[str]
    final_report: str

# 2. Define the Nodes
def architect_node(state: AgentState):
    print("[Council] Architect (405B) is starting review...", flush=True)
    llm = ChatNVIDIA(model="meta/llama-3.1-405b-instruct", temperature=0.1)
    prompt = [
        SystemMessage(content="You are the Lead System Architect. Evaluate the following documentation for structural integrity and modularity."),
        HumanMessage(content=f"Docs:\n{state['context']}\n\nProvide your top 3 concerns.")
    ]
    response = llm.invoke(prompt)
    print("[Council] Architect finished.", flush=True)
    return {"messages": [response], "critiques": [f"Architect: {response.content}"]}

def security_node(state: AgentState):
    print("[Council] Security (70B) is starting review...", flush=True)
    llm = ChatNVIDIA(model="meta/llama-3.1-70b-instruct", temperature=0.1)
    prompt = [
        SystemMessage(content="You are the Clinical Security Officer. Focus on PII/PHI isolation and safety protocols."),
        HumanMessage(content=f"Docs:\n{state['context']}\n\nIdentify 2 critical security or safety flaws.")
    ]
    response = llm.invoke(prompt)
    print("[Council] Security finished.", flush=True)
    return {"messages": [response], "critiques": [f"Security: {response.content}"]}

def summarizer_node(state: AgentState):
    print("[Council] Summarizer (405B) is starting...", flush=True)
    llm = ChatNVIDIA(model="meta/llama-3.1-405b-instruct", temperature=0.2)
    combined_critiques = "\n\n".join(state['critiques'])
    prompt = [
        SystemMessage(content="You are the Council Chair. Summarize all critiques into a final 'Consensus Report' with actionable steps."),
        HumanMessage(content=f"Critiques:\n{combined_critiques}")
    ]
    response = llm.invoke(prompt)
    print("[Council] Consensus reached.", flush=True)
    return {"final_report": response.content}

# 3. Build the Graph
workflow = StateGraph(AgentState)
workflow.add_node("architect", architect_node)
workflow.add_node("security", security_node)
workflow.add_node("summarizer", summarizer_node)

workflow.set_entry_point("architect")
workflow.add_edge("architect", "security")
workflow.add_edge("security", "summarizer")
workflow.add_edge("summarizer", END)

app = workflow.compile()

# 4. Utilities
def fetch_note_by_prefix(prefix: str):
    headers = {"Authorization": f"Bearer {OBSIDIAN_KEY}"}
    try:
        url = f"{OBSIDIAN_URL}/vault/{PROJECT_PATH}/"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            notes = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict): notes.append(item.get("name", ""))
                    elif isinstance(item, str): notes.append(item)
            elif isinstance(data, dict):
                notes = data.get("files", [])

            for n in notes:
                if n.startswith(f"{prefix} "):
                    content = requests.get(f"{OBSIDIAN_URL}/vault/{PROJECT_PATH}/{n}", headers=headers, timeout=5).text
                    return n, content
    except Exception as e:
        print(f"Error fetching {prefix}: {e}", flush=True)
    return None, None

def run_orchestration(task: str, prefixes: List[str]):
    print(f"--- TASK: {task} ---", flush=True)
    print("--- Ingesting Context ---", flush=True)
    context = ""
    for p in prefixes:
        name, text = fetch_note_by_prefix(p)
        if text:
            context += f"\n\n--- {name} ---\n{text}"
            print(f"Loaded: {name}", flush=True)

    if not context:
        print("Error: No context files found.", flush=True)
        return

    print("--- Executing LangGraph Orchestration ---", flush=True)
    initial_state = {"messages": [], "context": context, "critiques": [], "final_report": ""}
    final_output = app.invoke(initial_state)

    report_name = f"27 - Council Report - {task.replace(' ', '_')}.md"
    report_path = f"{PROJECT_PATH}/{report_name}"
    headers = {"Authorization": f"Bearer {OBSIDIAN_KEY}", "Content-Type": "text/markdown"}
    requests.put(f"{OBSIDIAN_URL}/vault/{report_path}", headers=headers, data=final_output['final_report'].encode('utf-8'), timeout=10)
    print(f"Orchestration complete! Report saved: {report_path}", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default="Architectural Review")
    parser.add_argument("prefixes", nargs="+")
    args = parser.parse_args()
    run_orchestration(args.task, args.prefixes)
