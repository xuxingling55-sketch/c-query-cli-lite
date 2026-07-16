from datetime import date
import json
from pathlib import Path
import unittest

from review_pack.models import ModuleResult, ReviewPackResult, ReviewRequest
from review_pack.validation import validate_pack


SNAPSHOT = Path(
    "outputs/review_pack/20260716_181630_785382_暑促/review_pack.json"
)


class RealSnapshotRegressionTest(unittest.TestCase):
    @unittest.skipUnless(SNAPSHOT.is_file(), "真实快照只在验收工作区运行")
    def test_validation_removes_737_false_failures_but_keeps_two_real_rates(self):
        payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        request_payload = payload["request"]
        request = ReviewRequest(
            name=request_payload["name"],
            start=date.fromisoformat(request_payload["start"]),
            end=date.fromisoformat(request_payload["end"]),
            last_year_start=date.fromisoformat(request_payload["last_year_start"]),
            last_year_end=date.fromisoformat(request_payload["last_year_end"]),
            target_amount=request_payload["target_amount"],
            deposit_source_start=date.fromisoformat(
                request_payload["deposit_source_start"]
            ),
            deposit_source_end=date.fromisoformat(
                request_payload["deposit_source_end"]
            ),
            reservoir_source_start=date.fromisoformat(
                request_payload["reservoir_source_start"]
            ),
            reservoir_source_end=date.fromisoformat(
                request_payload["reservoir_source_end"]
            ),
        )
        result = ReviewPackResult(
            request=request,
            modules={
                name: ModuleResult(
                    module=name,
                    status=module["status"],
                    rows=module["rows"],
                    error=module.get("error", ""),
                    source_version=module.get("source_version", "v1"),
                )
                for name, module in payload["modules"].items()
            },
        )

        original_failures = [
            check for check in payload["checks"] if check["status"] == "failed"
        ]
        self.assertEqual(len(original_failures), 739)

        checks = validate_pack(result)
        failures = [check for check in checks if check.status == "failed"]

        self.assertEqual(
            [(check.check_id, check.module) for check in failures],
            [
                ("percentage_range", "product_structure"),
                ("percentage_range", "product_structure"),
            ],
        )
        self.assertFalse(any(check.check_id == "channel_sum" for check in failures))
        self.assertFalse(any(check.check_id == "stage_unknown" for check in failures))
        self.assertEqual(
            len(
                [
                    check
                    for check in checks
                    if check.check_id == "stage_unknown_coverage"
                ]
            ),
            6,
        )


if __name__ == "__main__":
    unittest.main()
