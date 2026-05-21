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

    def chat(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict],
        last_user_images: list[tuple[str, bytes]],
        temperature: float,
        timeout: float | None = None,
    ) -> str:
        """Multi-turn chat completion with arbitrary message history.

        - `messages`: client-provided history, each {"role": "user"|"assistant", "content": str}.
          Server prepends its own system_prompt (clients can't override it for safety).
        - `last_user_images`: image bytes attached to the LAST user message only. Older
          turns reference images in text form (saves token cost across long conversations).
        - On vision-model rejection, caller should retry text-only by passing empty list.
        """
        chat_messages: list[dict] = [{"role": "system", "content": system_prompt}]
        last_user_idx = -1
        for i, m in enumerate(messages):
            if m.get("role") == "user":
                last_user_idx = i
        for i, m in enumerate(messages):
            role = m.get("role")
            text = m.get("content") or ""
            if role == "user" and i == last_user_idx and last_user_images:
                content: list[dict] = [{"type": "text", "text": text}]
                for mime, raw in last_user_images:
                    b64 = base64.b64encode(raw).decode("ascii")
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    })
                chat_messages.append({"role": "user", "content": content})
            else:
                chat_messages.append({"role": role, "content": text})

        kwargs = dict(
            model=model,
            messages=chat_messages,
            temperature=temperature,
        )
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
