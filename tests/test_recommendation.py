import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location('welcome', ROOT / 'welcome.py')
welcome = importlib.util.module_from_spec(spec)
spec.loader.exec_module(welcome)


class RecommendationTests(unittest.TestCase):
    def test_recommend_job_returns_top_k_matches(self):
        skills = ['python', 'flask', 'sql']
        recommendations = welcome.recommend_job(skills, algorithm='balanced', top_k=2)

        self.assertIsInstance(recommendations, list)
        self.assertLessEqual(len(recommendations), 2)
        self.assertTrue(recommendations)
        self.assertIn('title', recommendations[0])
        self.assertIn('score', recommendations[0])

    def test_ai_explanation_is_optional_and_uses_recommendation(self):
        recommendation = {
            'title': 'Python Developer',
            'description': 'Backend role',
            'skills': ['python', 'flask', 'aws'],
            'score': 0.9,
        }
        explanation = welcome.generate_ai_explanation(['python', 'flask'], recommendation, include_ai=False)
        self.assertIn('Python Developer', explanation)
        self.assertIn('python', explanation.lower())


if __name__ == '__main__':
    unittest.main()
