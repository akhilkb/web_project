import unittest

from Register import app


class RegisterPageTest(unittest.TestCase):
    def test_register_page_includes_login_button(self):
        client = app.test_client()
        response = client.get('/register')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Login', html)
        self.assertIn('href="/login"', html)


if __name__ == '__main__':
    unittest.main()
