"""Cross-language contract coverage for durable bubble identity and locks."""

import unittest

from src.core.config_models import BubbleState


class BubbleStateContractTests(unittest.TestCase):
    def test_legacy_bubble_state_remains_compatible(self) -> None:
        state = BubbleState.from_dict({
            "originalText": "原文",
            "coords": [1, 2, 30, 40],
        })

        self.assertEqual(state.bubble_id, "")
        self.assertEqual(state.manual_fields, [])
        self.assertEqual(state.to_dict()["bubbleId"], "")
        self.assertEqual(state.to_dict()["manualFields"], [])

    def test_identity_and_locks_round_trip_and_invalid_values_are_dropped(self) -> None:
        state = BubbleState.from_dict({
            "bubbleId": "bubble_7f2b",
            "manualFields": [
                "geometry",
                "translatedText",
                "not-a-contract-field",
                "geometry",
                42,
            ],
            "translatedText": "人工译文",
        })

        self.assertEqual(state.bubble_id, "bubble_7f2b")
        self.assertEqual(state.manual_fields, ["geometry", "translatedText"])
        self.assertEqual(state.to_dict()["manualFields"], ["geometry", "translatedText"])
        self.assertEqual(state.to_dict()["translatedText"], "人工译文")


if __name__ == "__main__":
    unittest.main()
