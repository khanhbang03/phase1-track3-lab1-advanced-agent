import pytest
from pydantic import ValidationError

from run_benchmark import expand_examples
from src.reflexion_lab.agents import ReActAgent, ReflexionAgent
from src.reflexion_lab.reporting import build_report
from src.reflexion_lab.schemas import JudgeResult, QAExample
from src.reflexion_lab.utils import load_dataset, normalize_answer


def test_normalize_answer_handles_articles_accents_and_punctuation():
    assert normalize_answer("  Thé River_Thames! ") == "river thames"


def test_judge_result_is_structured_and_strict():
    result = JudgeResult(score=1, reason="Equivalent answer.")
    assert result.missing_evidence == []
    with pytest.raises(ValidationError):
        JudgeResult(score=2, reason="Invalid score.")


def test_reflexion_records_failed_trace_and_then_recovers():
    example = next(item for item in load_dataset("data/hotpot_mini.json") if item.qid == "hp2")
    record = ReflexionAgent(max_attempts=3).run(example)
    assert record.is_correct
    assert record.attempts == 2
    assert len(record.reflections) == 1
    assert record.traces[0].reflection == record.reflections[0]
    assert record.traces[1].reflection is None


def test_react_only_attempts_once():
    example = next(item for item in load_dataset("data/hotpot_mini.json") if item.qid == "hp2")
    record = ReActAgent().run(example)
    assert not record.is_correct
    assert record.attempts == 1
    assert record.failure_mode == "incomplete_multi_hop"


def test_expand_examples_is_deterministic_and_does_not_mutate_source():
    source = load_dataset("data/hotpot_mini.json")[:2]
    expanded = expand_examples(source, 5)
    assert len(expanded) == 5
    assert source[0].qid == "hp1"
    assert expanded[0].qid == "hp1__repeat_1"
    assert expanded[-1].qid == "hp1__repeat_3"


def test_report_has_analysis_shape_expected_by_autograder():
    examples: list[QAExample] = load_dataset("data/hotpot_mini.json")
    records = [ReActAgent().run(item) for item in examples]
    records += [ReflexionAgent().run(item) for item in examples]
    report = build_report(records, "hotpot_mini.json")
    assert len(report.failure_modes) >= 3
    assert len(report.discussion) >= 250
    assert {"react", "reflexion"} <= set(report.summary)


def test_load_dataset_accepts_original_hotpot_schema(tmp_path):
    path = tmp_path / "hotpot.json"
    path.write_text(
        '[{"_id":"q1","level":"hard","question":"Q?","answer":"A",'
        '"context":[["Title",["Sentence one.","Sentence two."]]]}]',
        encoding="utf-8",
    )
    example = load_dataset(path)[0]
    assert example.qid == "q1"
    assert example.gold_answer == "A"
    assert example.context[0].text == "Sentence one. Sentence two."
