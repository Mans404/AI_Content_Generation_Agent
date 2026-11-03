import os

import dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig
from pydantic import create_model, conlist

from src.schemas.doctor_agent import AgentOutput, DoctorContext
from src.prompt_loader import PromptLoader


dotenv.load_dotenv()

prompts = PromptLoader()


model = init_chat_model(
    model="gpt-4o-mini",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)


class DoctorAgent:

    async def start(self, Doctor: DoctorContext) -> AgentOutput:
        expected_count = Doctor.posts_per_week * 4
        output_schema = create_model(
            "AgentOutputForRequestedPostCount",
            __base__=AgentOutput,
            ideas=(conlist(str, min_length=expected_count, max_length=expected_count), ...),
            post_types=(
                conlist(str, min_length=expected_count, max_length=expected_count),
                ...,
            ),
        )
        agent = create_agent(
            model=model,
            system_prompt=prompts.system(),
            response_format=output_schema,
        )

        user_prompt = prompts.user(
            doctor_name=Doctor.doctor_name,
            doctor_specialization=Doctor.doctor_specialization,
            language=Doctor.language,
            audiences=Doctor.audiences,
            types_of_medical_procedures=Doctor.types_of_medical_procedures,
            doctor_offers=Doctor.doctor_offers,
            advice_and_matters_that_most_people_find_confusing=(
                Doctor.advice_and_matters_that_most_people_find_confusing
            ),
            strengths=Doctor.strengths,
            posts_per_week=Doctor.posts_per_week,
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

        structured_response = response["structured_response"]
        response_data = (
            structured_response.model_dump()
            if isinstance(structured_response, AgentOutput)
            else structured_response
        )
        return AgentOutput.model_validate(
            response_data,
            context={"posts_per_week": Doctor.posts_per_week},
        )


doctor_agent = DoctorAgent()