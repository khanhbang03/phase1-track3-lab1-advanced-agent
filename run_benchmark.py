from __future__ import annotations
import json
from math import ceil
from pathlib import Path
import typer
from rich import print
from src.reflexion_lab.agents import ReActAgent, ReflexionAgent
from src.reflexion_lab.reporting import build_report, save_report
from src.reflexion_lab.runtime import MockRuntime, OpenAICompatibleRuntime
from src.reflexion_lab.schemas import QAExample
from src.reflexion_lab.utils import load_dataset, save_jsonl
app = typer.Typer(add_completion=False)

def expand_examples(examples: list[QAExample], target_count: int) -> list[QAExample]:
    """Repeat a small smoke dataset deterministically without mutating its items."""
    if target_count < 1:
        raise ValueError("target_count must be at least 1")
    if len(examples) >= target_count:
        return examples
    repeats = ceil(target_count / len(examples))
    expanded: list[QAExample] = []
    for repeat_id in range(1, repeats + 1):
        for example in examples:
            if len(expanded) == target_count:
                return expanded
            clone = example.model_copy(deep=True)
            clone.qid = f"{example.qid}__repeat_{repeat_id}"
            expanded.append(clone)
    return expanded

@app.command()
def main(
    dataset: str = "data/hotpot_mini.json",
    out_dir: str = "outputs/sample_run",
    reflexion_attempts: int = 3,
    min_records: int = 100,
    max_examples: int = 50,
    mode: str = "mock",
    model: str | None = None,
    base_url: str | None = None,
) -> None:
    if reflexion_attempts < 1:
        raise typer.BadParameter("--reflexion-attempts must be at least 1")
    if min_records < 2:
        raise typer.BadParameter("--min-records must be at least 2")
    if max_examples < 1:
        raise typer.BadParameter("--max-examples must be at least 1")
    if mode not in {"mock", "llm"}:
        raise typer.BadParameter("--mode must be 'mock' or 'llm'")
    source_examples = load_dataset(dataset)
    selected_examples = source_examples[:max_examples]
    examples = expand_examples(selected_examples, ceil(min_records / 2))
    runtime = MockRuntime() if mode == "mock" else OpenAICompatibleRuntime(model=model, base_url=base_url)
    react = ReActAgent(runtime=runtime)
    reflexion = ReflexionAgent(max_attempts=reflexion_attempts, runtime=runtime)
    react_records = [react.run(example) for example in examples]
    reflexion_records = [reflexion.run(example) for example in examples]
    all_records = react_records + reflexion_records
    out_path = Path(out_dir)
    save_jsonl(out_path / "react_runs.jsonl", react_records)
    save_jsonl(out_path / "reflexion_runs.jsonl", reflexion_records)
    report = build_report(all_records, dataset_name=Path(dataset).name, mode=runtime.mode)
    report.meta["source_examples"] = len(source_examples)
    report.meta["selected_examples"] = len(selected_examples)
    report.meta["evaluated_examples"] = len(examples)
    report.meta["dataset_repeated"] = len(examples) > len(selected_examples)
    json_path, md_path = save_report(report, out_path)
    print(f"[green]Saved[/green] {json_path}")
    print(f"[green]Saved[/green] {md_path}")
    print(json.dumps(report.summary, indent=2))

if __name__ == "__main__":
    app()
