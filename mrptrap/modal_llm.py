"""
Modal LLM Server — A100 GPU
============================
Serves LLM pricing agents via vLLM on an A100-80GB for the MRP Trap
seller agent experiments. All inference stays on Modal — no external API keys needed.

Architecture:
  - vLLM high-throughput batched inference
  - Modal Volume caches model weights so subsequent runs are instant
  - Default: Qwen/Qwen2.5-32B-Instruct (Apache 2.0 ungated, no tokens/keys required)
  - Configurable to meta-llama/Llama-3.3-70B-Instruct or any HuggingFace model

Cost: A100-80GB = $3.70/hr on Modal (~$0.06/min)
"""

from __future__ import annotations

import os
import modal

app = modal.App("mrptrap")

# Persistent volume — model weights are cached here after first download
volume = modal.Volume.from_name("mrptrap-model-cache", create_if_missing=True)
results_volume = modal.Volume.from_name("mrptrap-results", create_if_missing=True)

MODEL_DIR = "/models"
RESULTS_DIR = "/results"

# Default to Qwen2.5-32B (ungated, state-of-the-art reasoning, no HF token needed)
# Can be overridden via env var MRPTRAP_MODEL
MODEL_ID = os.environ.get("MRPTRAP_MODEL", "Qwen/Qwen2.5-32B-Instruct")

GPU_CONFIG = "A100-80GB"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm==0.6.4",
        "huggingface-hub>=0.24.0",
        "hf-transfer>=0.1.6",
    )
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "HUGGINGFACE_HUB_CACHE": MODEL_DIR,
        "HF_HOME": MODEL_DIR,
    })
)


@app.cls(
    gpu=GPU_CONFIG,
    image=image,
    volumes={MODEL_DIR: volume},
    timeout=3600,
    scaledown_window=600,  # keep warm for 10 min between calls
)
class LlamaServer:
    """
    vLLM-based inference server on Modal A100.
    Stays warm between calls so weights aren't reloaded across rounds.
    """

    @modal.enter()
    def setup(self):
        from vllm import LLM, SamplingParams
        import torch

        print(f"[ModelServer] Loading {MODEL_ID} on {torch.cuda.get_device_name(0)}")
        self.llm = LLM(
            model=MODEL_ID,
            download_dir=MODEL_DIR,
            dtype="bfloat16",
            max_model_len=4096,
            gpu_memory_utilization=0.90,
            enable_prefix_caching=True,  # cache system prompt across seller calls
        )
        self.tokenizer = self.llm.get_tokenizer()
        self.SamplingParams = SamplingParams
        print(f"[ModelServer] Ready ✓")

    @modal.method()
    def generate(
        self,
        prompts: list[str],
        system: str = (
            "You are a pricing agent for an ONDC seller. "
            "Respond ONLY with valid JSON: {\"price\": <float>, \"rationale\": \"<one sentence>\"}. "
            "No markdown, no explanation — just the JSON object."
        ),
        temperature: float = 0.7,
        max_tokens: int = 120,
    ) -> list[str]:
        """
        Batch inference: takes a list of user prompts, returns a list of responses.
        Batching all sellers in a round together maximises GPU utilisation.
        """
        from vllm import SamplingParams

        formatted = []
        for p in prompts:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": p},
            ]
            formatted.append(
                self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
            )

        params = SamplingParams(
            temperature=temperature,
            max_tokens=max_tokens,
        )
        outputs = self.llm.generate(formatted, params, use_tqdm=False)
        return [o.outputs[0].text.strip() for o in outputs]

    @modal.method()
    def generate_with_logprobs(
        self,
        prompts: list[str],
        system: str = (
            "You are a pricing agent for an ONDC seller. "
            "Respond ONLY with valid JSON: {\"price\": <float>, \"rationale\": \"<one sentence>\"}. "
            "No markdown, no explanation — just the JSON object."
        ),
        temperature: float = 0.0,
        max_tokens: int = 120,
        top_logprobs: int = 5,
    ) -> list[dict]:
        """
        Greedy decode with log-probabilities — used for mechanistic analysis
        to measure how much the first price token probability mass shifts
        when maximum_value is visible vs hidden.
        """
        from vllm import SamplingParams

        formatted = []
        for p in prompts:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": p},
            ]
            formatted.append(
                self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
            )

        params = SamplingParams(
            temperature=temperature,
            max_tokens=max_tokens,
            logprobs=top_logprobs,
        )
        outputs = self.llm.generate(formatted, params, use_tqdm=False)

        results = []
        for o in outputs:
            text = o.outputs[0].text.strip()
            first_logprobs = {}
            if o.outputs[0].logprobs:
                first_lp = o.outputs[0].logprobs[0]
                first_logprobs = {
                    tok_id: lp.logprob
                    for tok_id, lp in first_lp.items()
                }
            results.append({"text": text, "first_token_logprobs": first_logprobs})
        return results
