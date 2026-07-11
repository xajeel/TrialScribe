from trialscribe_ai.models.schemas import AgentState
from trialscribe_ai.agents.researcher import ResearchAgent
from trialscribe_ai.agents.planner import planner_agent
from trialscribe_ai.agents.writer import build_writer_agent
from trialscribe_ai.core.llm import llm

from langgraph.graph import StateGraph, END


#  ####### Research Agent ########
research_agent = ResearchAgent(llm)

async def research_agent_node(state: AgentState):
    sections = state.sections
    await research_agent.research_all_sections(sections)
    return {}

def graph_builder():
    graph = StateGraph(AgentState)

    graph.add_node( "planner_node", planner_agent)
    graph.add_node("research_node", research_agent_node)
    graph.add_node("writer_node", build_writer_agent)

    graph.set_entry_point("planner_node")
    graph.add_edge("planner_node", "research_node")
    graph.add_edge("research_node", "writer_node")
    graph.add_edge("writer_node", END)

    agent = graph.compile()
    return agent


if __name__ == "__main__":
    graph_builder()
