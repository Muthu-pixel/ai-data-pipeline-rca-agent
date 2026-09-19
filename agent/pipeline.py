import json
from openai import OpenAI
from config.settings import openai_api_key, model_name

client = OpenAI(api_key=openai_api_key)

RCA_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "report_rca",
        "description": "Report the root cause analysis and fix for a pipeline failure.",
        "parameters": {
            "type": "object",
            "properties": {
                "error_msg": {
                    "type": "string",
                    "description": "A concise one-line summary of the error."
                },
                "rca_steps": {
                    "type": "string",
                    "description": "Step-by-step explanation of the likely root cause."
                },
                "step_to_fix": {
                    "type": "string",
                    "description": "Concrete steps to fix the issue."
                },
            },
            "required": ["error_msg", "rca_steps", "step_to_fix"],
            "additionalProperties": False,
        },
    },
}


def get_rca_analysis(error_text: str) -> dict:
    """Returns a dict with error_msg, rca_steps, step_to_fix."""
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "user", "content": f"Analyze this pipeline failure:\n\n{error_text}"}
        ],
        tools=[RCA_TOOL_SCHEMA],
        tool_choice={"type": "function", "function": {"name": "report_rca"}},
    )

    message = response.choices[0].message
    if not message.tool_calls:
        return {"error_msg": "No tool call returned", "rca_steps": "N/A", "step_to_fix": "N/A"}

    try:
        return json.loads(message.tool_calls[0].function.arguments)
    except json.JSONDecodeError:
        return {"error_msg": "Failed to parse tool arguments", "rca_steps": "N/A", "step_to_fix": "N/A"}