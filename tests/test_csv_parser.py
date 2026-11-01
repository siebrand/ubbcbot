import unittest

from utils.csv_parser import CSVParser


class TestCSVParser(unittest.TestCase):
    """Test CSV parser for import functionality"""

    def test_valid_csv(self):
        """Test parsing valid CSV"""
        csv_content = b"offer_id,username\n123,alice\n456,bob"
        result = CSVParser.parse_import_csv(csv_content)

        self.assertTrue(result["success"])
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(result["rows"][0]["offer_id"], "123")
        self.assertEqual(result["rows"][0]["username"], "alice")
        self.assertEqual(result["rows"][1]["offer_id"], "456")
        self.assertEqual(result["rows"][1]["username"], "bob")

    def test_empty_file(self):
        """Test empty CSV file"""
        csv_content = b"offer_id,username\n"
        result = CSVParser.parse_import_csv(csv_content)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "empty_file")

    def test_no_content(self):
        """Test CSV with no content"""
        csv_content = b""
        result = CSVParser.parse_import_csv(csv_content)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "invalid_headers")

    def test_invalid_headers(self):
        """Test CSV with wrong headers"""
        csv_content = b"id,user\n123,alice"
        result = CSVParser.parse_import_csv(csv_content)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "invalid_headers")

    def test_empty_cell(self):
        """Test CSV with empty cell"""
        csv_content = b"offer_id,username\n123,alice\n456,"
        result = CSVParser.parse_import_csv(csv_content)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "empty_cell")
        self.assertEqual(result["line"], 3)
        self.assertEqual(result["field"], "username")

    def test_too_many_lines(self):
        """Test CSV exceeding line limit"""
        rows = ["offer_id,username"]
        for i in range(301):
            rows.append(f"{i},user{i}")
        csv_content = "\n".join(rows).encode("utf-8")

        result = CSVParser.parse_import_csv(csv_content)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "too_many_lines")
        self.assertEqual(result["line_count"], 302)

    def test_encoding_error(self):
        """Test CSV with invalid UTF-8 encoding"""
        csv_content = b"offer_id,username\n123,\xff\xfe"
        result = CSVParser.parse_import_csv(csv_content)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "encoding_error")

    def test_whitespace_in_cells(self):
        """Test CSV with whitespace (should be preserved in parsing)"""
        csv_content = b"offer_id,username\n 123 , alice "
        result = CSVParser.parse_import_csv(csv_content)

        self.assertTrue(result["success"])
        self.assertEqual(result["rows"][0]["offer_id"], " 123 ")
        self.assertEqual(result["rows"][0]["username"], " alice ")

    def test_duplicate_rows(self):
        """Test CSV with duplicate rows (should be allowed)"""
        csv_content = b"offer_id,username\n123,alice\n123,alice"
        result = CSVParser.parse_import_csv(csv_content)

        self.assertTrue(result["success"])
        self.assertEqual(len(result["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
