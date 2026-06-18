from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable
from .schemas import QAExample, RunRecord

def normalize_answer(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("answer must be a string")
    text = unicodedata.normalize("NFKD", text).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def load_dataset(path: str | Path) -> list[QAExample]:
    dataset_path = Path(path)
    raw = json.loads(dataset_path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"dataset must be a non-empty JSON array: {dataset_path}")
    return [_parse_example(item) for item in raw]

def _parse_example(item: object) -> QAExample:
    if not isinstance(item, dict):
        raise ValueError("each dataset item must be a JSON object")
    if {"qid", "difficulty", "question", "gold_answer", "context"} <= item.keys():
        return QAExample.model_validate(item)
    if {"_id", "level", "question", "answer", "context"} <= item.keys():
        context = []
        for chunk in item["context"]:
            if not isinstance(chunk, list) or len(chunk) != 2:
                raise ValueError("invalid HotpotQA context entry")
            title, sentences = chunk
            text = " ".join(sentences) if isinstance(sentences, list) else str(sentences)
            context.append({"title": title, "text": text})
        return QAExample.model_validate(
            {
                "qid": item["_id"],
                "difficulty": item["level"],
                "question": item["question"],
                "gold_answer": item["answer"],
                "context": context,
            }
        )
    raise ValueError("unsupported dataset schema; expected lab or HotpotQA format")

def save_jsonl(path: str | Path, records: Iterable[RunRecord]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(record.model_dump_json() + "\n")
