import unittest
from src.agents.scout import clean_url, generate_id

class TestScoutAgent(unittest.TestCase):
    def test_clean_url(self):
        # Should strip query params
        raw = "https://www.linkedin.com/jobs/view/123456/?trackingId=abc&refId=123"
        cleaned = clean_url(raw)
        self.assertEqual(cleaned, "https://www.linkedin.com/jobs/view/123456/")
        
        # Should work with no query params
        raw2 = "https://www.linkedin.com/jobs/view/99999/"
        cleaned2 = clean_url(raw2)
        self.assertEqual(cleaned2, "https://www.linkedin.com/jobs/view/99999/")
        
    def test_generate_id(self):
        url = "https://www.linkedin.com/jobs/view/123456/"
        title = "Software Engineer"
        company = "Tech Corp"
        
        job_id = generate_id(url, title, company)
        
        # Should be a 12-char hex string
        self.assertEqual(len(job_id), 12)
        
        # Should be consistent
        job_id2 = generate_id(url, title, company)
        self.assertEqual(job_id, job_id2)
        
        # Should differ if company differs
        job_id3 = generate_id(url, title, "Other Corp")
        self.assertNotEqual(job_id, job_id3)

if __name__ == '__main__':
    unittest.main()
