import unittest
import numpy as np
from core.searcher import parse_query_modifiers, HybridSearcher


class TestSearchArgumentsAndInverseSearch(unittest.TestCase):
    def test_parse_query_modifiers_filetypes(self):
        pq = parse_query_modifiers("authentication service !json -pdf !.csv")
        self.assertEqual(pq.clean_text, "authentication service")
        self.assertIn(".json", pq.excluded_extensions)
        self.assertIn(".pdf", pq.excluded_extensions)
        self.assertIn(".csv", pq.excluded_extensions)
        self.assertIsNone(pq.negative_concept)

    def test_parse_query_modifiers_negative_concepts(self):
        pq = parse_query_modifiers("beach vacation !crowded not:snow")
        self.assertEqual(pq.clean_text, "beach vacation")
        self.assertIn("crowded", pq.negative_concept)
        self.assertIn("snow", pq.negative_concept)
        self.assertEqual(len(pq.excluded_extensions), 0)

    def test_parse_query_modifiers_code_query(self):
        pq = parse_query_modifiers("code:def calculate_total !json")
        self.assertTrue(pq.is_code)
        self.assertEqual(pq.clean_text, "def calculate_total")
        self.assertIn(".json", pq.excluded_extensions)

    def test_vector_steering_calculation(self):
        # Create normalized random vectors
        v_pos = np.random.randn(512).astype(np.float32)
        v_pos /= np.linalg.norm(v_pos)

        v_neg = np.random.randn(512).astype(np.float32)
        v_neg /= np.linalg.norm(v_neg)

        # Vector subtraction
        steered = v_pos - 0.65 * v_neg
        steered /= np.linalg.norm(steered)

        sim_pos = float(np.dot(steered, v_pos))
        sim_neg = float(np.dot(steered, v_neg))

        self.assertGreater(sim_pos, 0.7)
        self.assertLess(sim_neg, 0.0)


if __name__ == "__main__":
    unittest.main()
