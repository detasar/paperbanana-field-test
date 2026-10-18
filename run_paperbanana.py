#!/usr/bin/env python3
"""Run the PaperBanana diagram pipeline on one method section and record its cost.

This is a thin wrapper around an unmodified checkout of the upstream project
(https://github.com/dwzhu-pku/PaperBanana). It reuses the upstream agents and
prompts as they are and adds three things:

* token-usage logging for every OpenAI call, converted to a USD estimate with
  the list prices in ``PRICES_PER_MILLION``;
* export of every intermediate render (planner, stylist, each critic round)
  plus the final figure as PNG;
* an optional "lite" retrieval mode that truncates each reference paper's
  methodology text in the retrieval prompt (see ``enable_lite_retrieval``).

The API key is read by the upstream code from the ``OPENAI_API_KEY``
environment variable. This script never reads, prints or stores its value.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_UPSTREAM_DIR = SCRIPT_DIR / "upstream" / "PaperBanana"
TASK = "diagram"

# USD per 1M tokens, OpenAI standard tier list prices (checked 2026-10-18).
# Costs reported by this script are estimates; your invoice is authoritative.
PRICES_PER_MILLION: dict[str, dict[str, float]] = {
    "gpt-5.4": {"input": 2.50, "cached": 0.25, "output": 15.00},
    "gpt-5.4-mini": {"input": 0.75, "cached": 0.075, "output": 4.50},
    "gpt-image-2": {"text_input": 5.00, "image_input": 8.00, "output": 30.00},
}


class UsageRecorder:
    """Collects per-call token counts and cost estimates (no request metadata)."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def add(self, record: dict[str, Any]) -> None:
        self.records.append(record)

    def summary(self) -> dict[str, Any]:
        chat = [r for r in self.records if r["kind"] == "chat"]
        image = [r for r in self.records if r["kind"] == "image"]
        chat_usd = sum(r["usd"] for r in chat)
        image_usd = sum(r["usd"] for r in image)
        return {
            "chat_calls": len(chat),
            "image_calls": len(image),
            "chat_usd": round(chat_usd, 4),
            "image_usd": round(image_usd, 4),
            "total_usd": round(chat_usd + image_usd, 4),
        }


def _attr(obj: Any, name: str) -> int:
    return int(getattr(obj, name, 0) or 0) if obj is not None else 0


def instrument_openai(recorder: UsageRecorder) -> None:
    """Wrap the async OpenAI chat and image endpoints to record token usage."""
    from openai.resources.chat.completions import AsyncCompletions
    from openai.resources.images import AsyncImages

    original_chat = AsyncCompletions.create
    original_image = AsyncImages.generate

    async def chat_create(self, *args, **kwargs):
        start = time.monotonic()
        response = await original_chat(self, *args, **kwargs)
        model = kwargs.get("model", "unknown")
        usage = getattr(response, "usage", None)
        prompt = _attr(usage, "prompt_tokens")
        completion = _attr(usage, "completion_tokens")
        cached = _attr(getattr(usage, "prompt_tokens_details", None), "cached_tokens")
        price = PRICES_PER_MILLION.get(model, {"input": 0, "cached": 0, "output": 0})
        usd = (
            (prompt - cached) * price["input"]
            + cached * price["cached"]
            + completion * price["output"]
        ) / 1e6
        recorder.add(
            {
                "kind": "chat",
                "model": model,
                "prompt_tokens": prompt,
                "cached_tokens": cached,
                "completion_tokens": completion,
                "usd": round(usd, 5),
                "seconds": round(time.monotonic() - start, 1),
            }
        )
        return response

    async def image_generate(self, *args, **kwargs):
        start = time.monotonic()
        response = await original_image(self, *args, **kwargs)
        model = kwargs.get("model", "unknown")
        usage = getattr(response, "usage", None)
        details = getattr(usage, "input_tokens_details", None)
        if details is not None:
            text_in = _attr(details, "text_tokens")
            image_in = _attr(details, "image_tokens")
        else:
            text_in, image_in = _attr(usage, "input_tokens"), 0
        output = _attr(usage, "output_tokens")
        price = PRICES_PER_MILLION.get(model, {"text_input": 0, "image_input": 0, "output": 0})
        usd = (
            text_in * price["text_input"]
            + image_in * price["image_input"]
            + output * price["output"]
        ) / 1e6
        recorder.add(
            {
                "kind": "image",
                "model": model,
                "size": kwargs.get("size"),
                "quality": kwargs.get("quality"),
                "text_input_tokens": text_in,
                "image_input_tokens": image_in,
                "output_tokens": output,
                "usd": round(usd, 5),
                "seconds": round(time.monotonic() - start, 1),
            }
        )
        return response

    AsyncCompletions.create = chat_create
    AsyncImages.generate = image_generate


def enable_lite_retrieval(max_chars: int) -> None:
    """Truncate reference methodology text inside the Retriever's prompt.

    By default the Retriever sends the full methodology sections of all 200
    PaperBananaBench reference papers in one prompt (~3M characters). Here the
    ``content`` field of each reference is cut to ``max_chars`` characters and
    suffixed with " [...]" when the Retriever loads ``ref.json``. Only the
    retriever module sees the truncated data; the Planner still loads the full
    references it was given. Prompts and parsing are unchanged.
    """
    import agents.retriever_agent as retriever_module

    real_json = retriever_module.json

    def load_truncated(fp, *args, **kwargs):
        data = real_json.load(fp, *args, **kwargs)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "content" in item:
                    item["content"] = f"{str(item['content'])[:max_chars]} [...]"
        return data

    retriever_module.json = SimpleNamespace(
        load=load_truncated, loads=real_json.loads, dumps=real_json.dumps
    )


def load_upstream_skill(upstream_dir: Path):
    """Import the upstream ``skill/run.py`` helpers as a module."""
    spec = importlib.util.spec_from_file_location(
        "paperbanana_skill", upstream_dir / "skill" / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save_png(b64_jpeg: str, path: Path) -> None:
    from PIL import Image

    Image.open(io.BytesIO(base64.b64decode(b64_jpeg))).convert("RGB").save(path)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    upstream_dir = args.upstream_dir.resolve()
    method_text = args.method_file.resolve().read_text(encoding="utf-8")
    caption = args.caption_file.resolve().read_text(encoding="utf-8").strip()
    out_dir = args.out_dir.resolve()
    (out_dir / "intermediate").mkdir(parents=True, exist_ok=True)

    # The upstream code resolves configs and data relative to its own root.
    sys.path.insert(0, str(upstream_dir))
    os.chdir(upstream_dir)

    recorder = UsageRecorder()
    instrument_openai(recorder)
    retrieval = args.retrieval
    if retrieval == "lite":
        enable_lite_retrieval(args.lite_chars)
        retrieval = "auto"

    skill = load_upstream_skill(upstream_dir)
    skill.ensure_model_config()
    skill.ensure_dataset(TASK)

    from agents.critic_agent import CriticAgent
    from agents.planner_agent import PlannerAgent
    from agents.polish_agent import PolishAgent
    from agents.retriever_agent import RetrieverAgent
    from agents.stylist_agent import StylistAgent
    from agents.vanilla_agent import VanillaAgent
    from agents.visualizer_agent import VisualizerAgent
    from utils import config
    from utils.legacy_generation_options import generation_additional_info
    from utils.paperviz_processor import PaperVizProcessor

    exp_config = config.ExpConfig(
        dataset_name="Demo",
        split_name="demo",
        exp_mode=args.exp_mode,
        retrieval_setting=retrieval,
        planner_metaphor=False,
        main_model_name=args.main_model,
        image_gen_model_name=args.image_model,
        work_dir=upstream_dir,
    )
    processor = PaperVizProcessor(
        exp_config=exp_config,
        vanilla_agent=VanillaAgent(exp_config=exp_config),
        planner_agent=PlannerAgent(exp_config=exp_config),
        visualizer_agent=VisualizerAgent(exp_config=exp_config),
        stylist_agent=StylistAgent(exp_config=exp_config),
        critic_agent=CriticAgent(exp_config=exp_config),
        retriever_agent=RetrieverAgent(exp_config=exp_config),
        polish_agent=PolishAgent(exp_config=exp_config),
    )
    queries = [
        {
            "filename": f"{args.name}_candidate{i}",
            "caption": caption,
            "content": method_text,
            "visual_intent": caption,
            "additional_info": generation_additional_info(args.aspect_ratio, None),
            "max_critic_rounds": args.critic_rounds,
        }
        for i in range(args.candidates)
    ]

    start = time.monotonic()
    results = [
        r
        async for r in processor.process_queries_batch(
            queries, max_concurrent=args.candidates, do_eval=False
        )
    ]
    wall_seconds = time.monotonic() - start

    for index, result in enumerate(results):
        prefix = f"candidate{index}"
        descriptions = {}
        for key, value in result.items():
            if key.endswith("_base64_jpg") and value:
                stem = key.removesuffix("_base64_jpg")
                save_png(value, out_dir / "intermediate" / f"{prefix}_{stem}.png")
            elif "base64" not in key and isinstance(value, (str, int, float, list, dict)):
                descriptions[key] = value
        (out_dir / f"{prefix}_descriptions.json").write_text(
            json.dumps(descriptions, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        final = skill.extract_final_image_b64(result, args.exp_mode)
        if final:
            name = "generated_final.png" if index == 0 else f"{prefix}_final.png"
            save_png(final, out_dir / name)

    summary = {
        "name": args.name,
        "main_model": args.main_model,
        "image_model": args.image_model,
        "exp_mode": args.exp_mode,
        "retrieval": args.retrieval,
        "lite_chars": args.lite_chars if args.retrieval == "lite" else None,
        "critic_rounds": args.critic_rounds,
        "candidates": args.candidates,
        "wall_seconds": round(wall_seconds, 1),
        **recorder.summary(),
    }
    (out_dir / "usage.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in recorder.records), encoding="utf-8"
    )
    (out_dir / "cost_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a methodology diagram with PaperBanana from a method-section "
            "text file and a caption, and log token usage and estimated cost."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--method-file",
        type=Path,
        required=True,
        help="Plain-text methodology section used as input.",
    )
    parser.add_argument(
        "--caption-file",
        type=Path,
        required=True,
        help="Plain-text figure caption (also used as visual intent).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Directory for the figure, intermediate renders and cost logs.",
    )
    parser.add_argument(
        "--name", default="figure", help="Short identifier used in output file names."
    )
    parser.add_argument(
        "--upstream-dir",
        type=Path,
        default=DEFAULT_UPSTREAM_DIR,
        help="Path to the PaperBanana checkout (see scripts/setup.sh).",
    )
    parser.add_argument(
        "--main-model",
        default="gpt-5.4",
        help="Model for the retriever, planner, stylist and critic agents.",
    )
    parser.add_argument(
        "--image-model", default="gpt-image-2", help="Image generation model for the visualizer."
    )
    parser.add_argument(
        "--exp-mode",
        default="demo_full",
        choices=["demo_planner_critic", "demo_full"],
        help="Upstream pipeline mode; demo_full includes the stylist.",
    )
    parser.add_argument(
        "--critic-rounds", type=int, default=3, help="Maximum number of critic refinement rounds."
    )
    parser.add_argument(
        "--candidates", type=int, default=1, help="Number of independent candidates to generate."
    )
    parser.add_argument(
        "--aspect-ratio", default="16:9", help="Aspect ratio hint passed to the pipeline."
    )
    parser.add_argument(
        "--retrieval",
        default="lite",
        choices=["lite", "auto", "random", "none"],
        help="'auto' is the upstream default; 'lite' is auto with truncated reference texts.",
    )
    parser.add_argument(
        "--lite-chars",
        type=int,
        default=600,
        help="Characters kept per reference methodology in lite mode.",
    )
    args = parser.parse_args(argv)
    if args.candidates < 1 or args.critic_rounds < 0 or args.lite_chars < 1:
        parser.error("--candidates and --lite-chars must be >= 1, --critic-rounds >= 0")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not os.environ.get("OPENAI_API_KEY"):
        print("error: OPENAI_API_KEY is not set in this shell.", file=sys.stderr)
        return 2
    for path in (args.method_file, args.caption_file):
        if not path.is_file():
            print(f"error: input file not found: {path}", file=sys.stderr)
            return 2
    if not (args.upstream_dir / "skill" / "run.py").is_file():
        print(
            f"error: PaperBanana checkout not found at {args.upstream_dir}; "
            "run scripts/setup.sh first.",
            file=sys.stderr,
        )
        return 2
    summary = asyncio.run(run(args))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
