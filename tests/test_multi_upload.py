"""
========================================================================================
Unit Tests: Multi-File & ZIP Upload Parsing (tests/test_multi_upload.py)
========================================================================================
"""

import io
import json
import zipfile
import unittest

from current_model.models.contract import Contract
from current_model.models.load_component import SimpleConsumer, consumers_to_drac
from current_model.ui.tab2_contract.form import _parse_uploaded_contract_files
from current_model.ui.tab1_consumption.synthetic.view import _parse_uploaded_profile_files


class MockUploadedFile:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data
        self.size = len(data)

    def getvalue(self) -> bytes:
        return self._data


class TestMultiUpload(unittest.TestCase):
    """Tests multi-file and zip archive parsing for contracts and synthetic profiles."""

    def test_parse_multiple_individual_contract_files(self):
        c1 = Contract(name="Contract Alpha", currency="EUR", contracted_capacity_kw=100.0)
        c2 = Contract(name="Contract Beta", currency="USD", contracted_capacity_kw=250.0)

        f1 = MockUploadedFile("c1.drac", c1.to_json().encode("utf-8"))
        f2 = MockUploadedFile("c2.json", c2.to_json().encode("utf-8"))

        parsed = _parse_uploaded_contract_files([f1, f2])
        self.assertEqual(len(parsed), 2)
        self.assertTrue(any("Contract Alpha" in k for k in parsed))
        self.assertTrue(any("Contract Beta" in k for k in parsed))

    def test_parse_contract_zip_archive(self):
        c1 = Contract(name="Tariff High Peak", currency="EUR", contracted_capacity_kw=500.0)
        c2 = Contract(name="Tariff Flat", currency="EUR", contracted_capacity_kw=300.0)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as z:
            z.writestr("contracts/high_peak.drac", c1.to_json())
            z.writestr("contracts/flat.json", c2.to_json())
            z.writestr("contracts/readme.txt", "This should be ignored.")

        zip_file = MockUploadedFile("all_contracts.zip", zip_buffer.getvalue())
        parsed = _parse_uploaded_contract_files([zip_file])

        self.assertEqual(len(parsed), 2)
        self.assertTrue(any("Tariff High Peak" in k for k in parsed))
        self.assertTrue(any("Tariff Flat" in k for k in parsed))

    def test_parse_synthetic_profile_zip_archive(self):
        c_list = [
            SimpleConsumer(name="Air Conditioner", category="Cooling", power_kw=10.0, count=2)
        ]
        profile_json = consumers_to_drac(c_list, profile_name="Office Summer")

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as z:
            z.writestr("summer.drac", profile_json)

        zip_file = MockUploadedFile("profiles.zip", zip_buffer.getvalue())
        parsed = _parse_uploaded_profile_files([zip_file])

        self.assertEqual(len(parsed), 1)
        self.assertIn("summer.drac", parsed)
        self.assertEqual(len(parsed["summer.drac"]), 1)
        self.assertEqual(parsed["summer.drac"][0].name, "Air Conditioner")


if __name__ == "__main__":
    unittest.main()
