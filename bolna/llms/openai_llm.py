import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

from .llm import BaseLLM
from bolna.helpers.logger_config import configure_logger

logger = configure_logger(__name__)
load_dotenv()


class OpenAiLLM(BaseLLM):
    def __init__(self, max_tokens=100, buffer_size=40, model="gpt-3.5-turbo-16k", temperature= 0.1, **kwargs):
        super().__init__(max_tokens, buffer_size)
        self.model = model
        self.started_streaming = False
        logger.info(f"Initializing OpenAI LLM with model: {self.model} and maxc tokens {max_tokens}")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.vllm_model = "vllm" in self.model
        self.model_args = { "max_tokens": self.max_tokens, "temperature": self.temperature, "model": self.model}
        if model == "Krutrim-spectre-v2":
            logger.info(f"Connecting to Ola's krutrim model")
            base_url = kwargs.get("base_url", os.getenv("OLA_KRUTRIM_BASE_URL"))
            api_key=kwargs.get('llm_key', None)
            if api_key is not None and len(api_key) > 0:
                api_key = api_key
            self.async_client = AsyncOpenAI( base_url=base_url, api_key= api_key)
        else:
            llm_key = kwargs.get('llm_key', os.getenv('OPENAI_API_KEY'))
            if llm_key != "sk-":
                llm_key = os.getenv('OPENAI_API_KEY')
            else:
                llm_key = kwargs['llm_key']
            self.async_client = AsyncOpenAI(api_key=llm_key)
            
    async def generate_stream(self, messages, synthesize=True, request_json=False):
        if len(messages) == 0:
            raise Exception("No messages provided")
        
        response_format = self.get_response_format(request_json)

        answer, buffer = "", ""
        logger.info(f"request to open ai {messages} max tokens {self.max_tokens} ")
        model_args = self.model_args
        model_args["response_format"] = response_format
        model_args["messages"] = messages
        model_args["stream"] = True
        model_args["stop"] = ["User:"]
        async for chunk in await self.async_client.chat.completions.create(**model_args):
            if text_chunk := chunk.choices[0].delta.content:
                answer += text_chunk
                buffer += text_chunk

                if len(buffer) >= self.buffer_size and synthesize:
                    buffer_words = buffer.split(" ")
                    text = ' '.join(buffer_words[:-1])

                    if not self.started_streaming:
                        self.started_streaming = True
                    yield text, False
                    buffer = buffer_words[-1]

        if synthesize: # This is used only in streaming sense 
            yield buffer, True
        else:
            yield answer, True
        self.started_streaming = False

    async def generate(self, messages, request_json=False):
        response_format = self.get_response_format(request_json)
        logger.info(f"request to open ai {messages}")

        completion = await self.async_client.chat.completions.create(model=self.model, temperature=0.0, messages=messages,
                                                                     stream=False, response_format=response_format)
        res = completion.choices[0].message.content
        return res

    def get_response_format(self, is_json_format: bool):
        if is_json_format and self.model in ('gpt-4-1106-preview', 'gpt-3.5-turbo-1106'):
            return {"type": "json_object"}
        else:
            return {"type": "text"}