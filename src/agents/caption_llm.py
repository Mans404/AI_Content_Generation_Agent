import os

import dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig
from pydantic import create_model, conlist

from src.prompt_loader import PromptLoader
from src.schemas.doctor_agent import CaptionOutput, DoctorContext


dotenv.load_dotenv()

prompts = PromptLoader()

model = init_chat_model(
    model="gpt-4o-mini",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)


class CaptionLLM:
    async def start(
        self,
        doctor: DoctorContext,
        ideas: list[str],
        post_types: list[str],
    ) -> CaptionOutput:
        if len(ideas) != len(post_types):
            raise ValueError("ideas and post_types must have the same length")
        if not ideas:
            raise ValueError("At least one idea is required to generate captions")

        output_schema = create_model(
            "CaptionOutputForRequestedIdeas",
            __base__=CaptionOutput,
            captions=(conlist(str, min_length=len(ideas), max_length=len(ideas)), ...),
        )
        agent = create_agent(
            model=model,
            system_prompt=prompts.caption_system(),
            response_format=output_schema,
        )
        user_prompt = prompts.caption_user(
            doctor_name=doctor.doctor_name,
            doctor_specialization=doctor.doctor_specialization,
            language=doctor.language,
            audiences=doctor.audiences,
            types_of_medical_procedures=doctor.types_of_medical_procedures,
            strengths=doctor.strengths,
            ideas=ideas,
            post_types=post_types,
        )
        config: RunnableConfig = {
            "configurable": {
                "thread_id": f"captions-{doctor.doctor_id}"
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
            if isinstance(structured_response, CaptionOutput)
            else structured_response
        )
        result = CaptionOutput.model_validate(response_data)
        if len(result.captions) != len(ideas):
            raise ValueError("The caption agent must return one caption for every idea.")
        return result


caption_llm = CaptionLLM()
