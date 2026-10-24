"""Prospective transfer evaluation keeps its own checked public interface."""

import unittest


class TransferEvaluationTests(unittest.TestCase):
    def test_public_transfer_interfaces_exist(self):
        from buddha.final_evaluation import (
            inspect_transfer_evaluation,
            run_transfer_evaluation,
        )

        self.assertTrue(callable(run_transfer_evaluation))
        self.assertTrue(callable(inspect_transfer_evaluation))


if __name__ == "__main__":
    unittest.main()
