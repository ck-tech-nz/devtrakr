import base64
import openai
from .models import LLMConfig


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = openai.OpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
        )

    def complete(self, model: str, system_prompt: str, user_prompt: str, temperature: float, timeout: float | None = None) -> str:
        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        if self.config.supports_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def complete_multimodal(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        images: list[tuple[str, bytes]],
        temperature: float,
        timeout: float | None = None,
    ) -> str:
        """Multimodal chat completion.

        `images` is a list of (mime_type, raw_bytes) tuples. When the list is
        empty the user message is sent as a plain string so the same call path
        works for text-only fallback after a vision-model failure.
        """
        if images:
            content: list[dict] = [{"type": "text", "text": user_prompt}]
            for mime, raw in images:
                b64 = base64.b64encode(raw).decode("ascii")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })
            user_message = {"role": "user", "content": content}
        else:
            user_message = {"role": "user", "content": user_prompt}

        kwargs = dict(
            model=model,
            messages=[{"role": "system", "content": system_prompt}, user_message],
            temperature=temperature,
        )
        # NOTE: DashScope's compatible-mode rejects response_format=json_object
        # on VL models. We rely on prompt instructions for clean JSON instead.
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
