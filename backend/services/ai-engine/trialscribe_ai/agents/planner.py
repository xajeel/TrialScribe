from trialscribe_ai.models.schemas import AgentState, Sections
from trialscribe_ai.core.llm import llm
from trialscribe_ai.prompts.templates import PromptFamily


def planner_agent(state: AgentState, model=llm):
    print("Planner Agent")

    query =  state.query
    summary = state.summary
    prompt = PromptFamily.planner_prompt(query=query, json_summary=summary)
    response = model.invoke([{"role": "user", "content": prompt}])

    model = model.with_structured_output(Sections)
    output = model.invoke([{"role": "user", "content": f"Make this to M11 report sections {response.content}"}])
    return {"sections": output.sections}
