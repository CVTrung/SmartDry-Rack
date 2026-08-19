import unittest

from scripts.create_account import get_location_preset


class CreateAccountScriptTests(unittest.TestCase):
    def test_returns_hcm_preset(self) -> None:
        preset = get_location_preset("LOCATION_HCM")

        self.assertEqual(preset.name, "Ho Chi Minh City")
        self.assertEqual(preset.latitude, 10.8231)
        self.assertEqual(preset.longitude, 106.6297)
        self.assertEqual(preset.timezone, "Asia/Ho_Chi_Minh")

    def test_returns_hanoi_preset(self) -> None:
        preset = get_location_preset("location_hanoi")

        self.assertEqual(preset.name, "Hanoi")
        self.assertEqual(preset.latitude, 21.0278)
        self.assertEqual(preset.longitude, 105.8342)

    def test_rejects_unknown_location(self) -> None:
        with self.assertRaises(SystemExit):
            get_location_preset("location_unknown")


if __name__ == "__main__":
    unittest.main()
