import csv
import io
import logging

logger = logging.getLogger()


class CSVParser:
    """Utility for parsing and validating CSV files for order import"""

    MAX_LINES = 300
    REQUIRED_HEADERS = ["offer_id", "username"]

    @staticmethod
    def parse_import_csv(file_content: bytes) -> dict:
        """
        Parse CSV file for order import

        Returns:
            dict with 'success', 'rows', and 'error' keys
        """
        try:
            # Decode UTF-8
            try:
                content_str = file_content.decode("utf-8")
            except UnicodeDecodeError:
                return {"success": False, "error": "encoding_error", "rows": []}

            # Count lines
            lines = content_str.strip().split("\n")
            if len(lines) > CSVParser.MAX_LINES:
                return {"success": False, "error": "too_many_lines", "rows": [], "line_count": len(lines)}

            # Parse CSV
            csv_file = io.StringIO(content_str)
            try:
                reader = csv.DictReader(csv_file)
            except csv.Error:
                return {"success": False, "error": "csv_parse_error", "rows": []}

            # Validate headers
            if not reader.fieldnames or set(reader.fieldnames) != set(CSVParser.REQUIRED_HEADERS):
                return {
                    "success": False,
                    "error": "invalid_headers",
                    "rows": [],
                    "expected": CSVParser.REQUIRED_HEADERS,
                    "found": reader.fieldnames,
                }

            # Parse rows
            rows = []
            for row in reader:
                rows.append(row)

            # Check for empty file (no data rows)
            if len(rows) == 0:
                return {"success": False, "error": "empty_file", "rows": []}

            # Validate all cells are filled
            for idx, row in enumerate(rows, start=2):  # Start at 2 (header is line 1)
                for header in CSVParser.REQUIRED_HEADERS:
                    if not row.get(header) or not row[header].strip():
                        return {"success": False, "error": "empty_cell", "rows": [], "line": idx, "field": header}

            return {"success": True, "rows": rows, "error": None}

        except Exception as e:
            logger.error(f"Unexpected error parsing CSV: {e}")
            return {"success": False, "error": "unexpected_error", "rows": []}
