import unittest

from pipeline.sources.public_comment import parse


class PublicComment(unittest.TestCase):
    def test_list_with_side(self):
        t = ("Upon the Chair's call for public comment, the following individuals appeared and expressed their concerns:\n\n"
             " Joe Gariboldi, Largo\n Suzy Orr, Largo\n Clara Murzynski, Largo (spoke on behalf of others)\n\n In rebuttal, the applicant spoke.")
        p = parse(t)
        self.assertEqual((p["speakers"], p["against"], p["groups"]), (3, 3, True))
        self.assertEqual(p["cities"], ["Largo"])

    def test_applicant_not_public(self):
        p = parse("Upon the Chair's call for public comment, Lauren Rubenstein, Tampa, appeared and indicated that she represents the property owner.")
        self.assertEqual((p["speakers"], p["applicant"]), (0, 1))

    def test_none_and_mail(self):
        p = parse("Resolution adopted. Five letters and three voicemails in opposition have been received. No citizens appeared to be heard.")
        self.assertEqual(p["speakers"], 0)
        self.assertTrue(p["mail"].startswith("Five letters"))

    def test_unrecorded(self):
        self.assertEqual(parse("The Board accepted public input on this matter.")["speakers"], "some")
        self.assertIsNone(parse("Motion to approve."))


if __name__ == "__main__":
    unittest.main()
