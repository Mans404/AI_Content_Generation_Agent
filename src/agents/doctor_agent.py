import os

import dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from src.schemas.doctor_agent import AgentOutput, DoctorContext
from src.prompt_loader import PromptLoader


dotenv.load_dotenv()

prompts = PromptLoader()


model = init_chat_model(
    model="gpt-4o-mini",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)


agent = create_agent(
    model=model,
    system_prompt=prompts.system(),
    response_format=AgentOutput,
)


class DoctorAgent:

    async def start(self, Doctor: DoctorContext) -> AgentOutput:

        user_prompt = prompts.user(
            doctor_name=Doctor.doctor_name,
            doctor_specialization=Doctor.doctor_specialization,
        )

        config: RunnableConfig = {
            "configurable": {
                "thread_id": str(Doctor.doctor_id)
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

        return response["structured_response"]


doctor_agent = DoctorAgent()