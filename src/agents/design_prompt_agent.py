import os

import dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig

from src.prompt_loader import PromptLoader
from src.schemas.doctor_agent import (
    AgentOutput,
    DesignPromptOutput,
    DoctorContext,
)


dotenv.load_dotenv()

prompts = PromptLoader()

model = init_chat_model(
    model="gpt-4o-mini",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)


class DesignPromptAgent:
    async def start(
        self,
        doctor: DoctorContext,
        agent_output: AgentOutput,
    ) -> DesignPromptOutput:
        agent = create_agent(
            model=model,
            system_prompt=prompts.design_system(),
            response_format=DesignPromptOutput,
        )
        user_prompt = prompts.design_user(
            doctor_name=doctor.doctor_name,
            doctor_specialization=doctor.doctor_specialization,
            language=doctor.language,
            audiences=doctor.audiences,
            ideas=agent_output.ideas,
            post_types=agent_output.post_types,
        )
        config: RunnableConfig = {
            "configurable": {
                "thread_id": f"design-prompts-{doctor.doctor_id}"
            }
        }
        response = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": user_prompt,
                    }
                ]
            },
            config=config,
        )
        structured_response = response["structured_response"]
        response_data = (
            structured_response.model_dump()
            if isinstance(structured_response, DesignPromptOutput)
            else structured_response
        )
        result = DesignPromptOutput.model_validate(response_data)
        if len(result.design_prompts) != len(agent_output.ideas):
            raise ValueError(
                "The design prompt agent must return one prompt for every idea."
            )
        return result


design_prompt_agent = DesignPromptAgent()
