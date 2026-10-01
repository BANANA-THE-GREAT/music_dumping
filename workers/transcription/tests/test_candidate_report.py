from vss_worker.candidate_report import summarize_candidates


def test_candidate_must_pass_every_preregistered_check() -> None:
    metric = {
        "onset_pitch": {"f1_macro": 0.7},
        "onset_offset_pitch": {
            "precision_macro": 0.6,
            "recall_macro": 0.44,
            "f1_macro": 0.51,
        },
    }
    report = {
        "quality_gate": {
            "candidate_onset_offset_f1_improvement": 0.03,
            "candidate_recall_improvement": 0.05,
            "maximum_precision_regression": 0.02,
            "maximum_failure_rate": 0.02,
        },
        "clips": [{"split": "holdout"}],
        "aggregate_by_split": {
            "holdout": {
                "basic_pitch_raw": {
                    "onset_pitch": {"f1_macro": 0.5},
                    "onset_offset_pitch": {
                        "precision_macro": 0.5,
                        "recall_macro": 0.4,
                        "f1_macro": 0.45,
                    },
                },
                "candidate": metric,
            }
        },
    }
    runtime = {
        "upstream_commit": "abc",
        "model_sha256": "123",
        "device": "cpu",
        "seed": 1,
        "model_load_seconds": 1,
        "inference_seconds": 2,
        "peak_rss_kib": 3,
        "clip_count": 1,
        "failures": [],
    }
    summary = summarize_candidates(report, {"candidate": runtime})
    checks = summary["candidates"]["candidate"]["quality_gate_checks"]
    assert checks["onset_offset_f1_improvement"] is True
    assert checks["recall_improvement"] is False
    assert checks["passed_all"] is False
