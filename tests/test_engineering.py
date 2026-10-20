import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from pcb_analyzer.engineering import (  # noqa: E402
    expected_range, fmt_engineering, ohms_law_current, ohms_law_resistance,
    ohms_law_voltage, parse_tolerance, parse_value, power,
    power_from_resistance, voltage_divider, within_tolerance,
)


class TestParseValue(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(parse_value("3.3"), 3.3)

    def test_with_unit(self):
        self.assertEqual(parse_value("3.3 V"), 3.3)

    def test_kilo(self):
        self.assertEqual(parse_value("4.7k"), 4700.0)

    def test_mega(self):
        self.assertEqual(parse_value("10M"), 1e7)

    def test_milli(self):
        self.assertAlmostEqual(parse_value("100m"), 0.1)

    def test_micro(self):
        self.assertAlmostEqual(parse_value("100µ"), 100e-6)
        self.assertAlmostEqual(parse_value("100u"), 100e-6)

    def test_nano(self):
        self.assertAlmostEqual(parse_value("100nF"), 100e-9)

    def test_exponent(self):
        self.assertEqual(parse_value("1e3"), 1000.0)

    def test_invalid(self):
        self.assertIsNone(parse_value(""))
        self.assertIsNone(parse_value("abc"))
        self.assertIsNone(parse_value(None))


class TestParseTolerance(unittest.TestCase):
    def test_percent(self):
        self.assertEqual(parse_tolerance("5%"), 5.0)

    def test_plus_minus(self):
        self.assertEqual(parse_tolerance("±5%"), 5.0)

    def test_plain_number(self):
        self.assertEqual(parse_tolerance("2"), 2.0)

    def test_invalid(self):
        self.assertIsNone(parse_tolerance("abc"))


class TestOhmsLaw(unittest.TestCase):
    def test_voltage(self):
        self.assertAlmostEqual(ohms_law_voltage(0.001, 4700), 4.7)

    def test_current(self):
        self.assertAlmostEqual(ohms_law_current(5.0, 1000), 0.005)

    def test_resistance(self):
        self.assertAlmostEqual(ohms_law_resistance(5.0, 0.005), 1000.0)

    def test_current_zero_resistance(self):
        with self.assertRaises(ValueError):
            ohms_law_current(5.0, 0)

    def test_resistance_zero_current(self):
        with self.assertRaises(ValueError):
            ohms_law_resistance(5.0, 0)


class TestPower(unittest.TestCase):
    def test_simple(self):
        self.assertAlmostEqual(power(5.0, 0.1), 0.5)

    def test_from_resistance(self):
        self.assertAlmostEqual(power_from_resistance(5.0, 100), 0.25)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            power_from_resistance(5.0, 0)


class TestVoltageDivider(unittest.TestCase):
    def test_equal(self):
        self.assertAlmostEqual(voltage_divider(10, 1000, 1000), 5.0)

    def test_asymmetric(self):
        self.assertAlmostEqual(voltage_divider(10, 2000, 1000), 10 * 1000 / 3000)

    def test_zero_total(self):
        with self.assertRaises(ValueError):
            voltage_divider(10, 0, 0)


class TestTolerance(unittest.TestCase):
    def test_within(self):
        self.assertTrue(within_tolerance(4.9, 5.0, 5))

    def test_outside(self):
        self.assertFalse(within_tolerance(4.0, 5.0, 5))

    def test_boundary(self):
        self.assertTrue(within_tolerance(4.75, 5.0, 5))
        self.assertTrue(within_tolerance(5.25, 5.0, 5))
        self.assertFalse(within_tolerance(5.26, 5.0, 5))

    def test_zero_expected(self):
        self.assertTrue(within_tolerance(0.0, 0.0, 5))
        self.assertFalse(within_tolerance(0.1, 0.0, 5))

    def test_range(self):
        lo, hi = expected_range(5.0, 5)
        self.assertAlmostEqual(lo, 4.75)
        self.assertAlmostEqual(hi, 5.25)


class TestFormat(unittest.TestCase):
    def test_kilo(self):
        self.assertIn("4.7", fmt_engineering(4700, "Ω"))
        self.assertIn("k", fmt_engineering(4700, "Ω"))

    def test_micro(self):
        s = fmt_engineering(100e-6, "F")
        self.assertIn("100", s)
        self.assertIn("µ", s)

    def test_zero(self):
        self.assertEqual(fmt_engineering(0, "V"), "0 V")


if __name__ == "__main__":
    unittest.main()
