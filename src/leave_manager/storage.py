"""Reading and writing the leave data file.

The store owns the data and the file path. Nothing else in the package
touches the disk, and nothing is a global, so a test can make its own store
pointing at a temporary file.
"""
from pathlib import Path
from typing import Any
import json
import logging

log = logging.getLogger(__name__)

# Used only when the data file does not exist yet
SAMPLE_DATA: dict[str, dict[str, Any]] = {
    "E001": {"balance": 18, "history": ["2024-12-25", "2025-01-01"]},
    "E002": {"balance": 20, "history": []},
}


class LeaveStore:
    """The leave data, kept in memory and saved to a JSON file"""

    def __init__(self, path: Path, defaults: dict[str, dict[str, Any]] | None = None):
        self.path = Path(path)
        self._defaults = SAMPLE_DATA if defaults is None else defaults
        self._data = self._read()

    def _read(self) -> dict[str, dict[str, Any]]:
        if self.path.exists():
            log.info("Loading leave data from %s", self.path)
            return json.loads(self.path.read_text())
        log.info("No data file at %s, starting from sample data", self.path)
        return json.loads(json.dumps(self._defaults))  # a copy, not the original

    def save(self) -> None:
        """Write the current data to disk, creating the folder if needed"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))
        log.debug("Saved leave data to %s", self.path)

    def employees(self) -> dict[str, dict[str, Any]]:
        """Every employee record"""
        return self._data

    def __contains__(self, employee_id: str) -> bool:
        return employee_id in self._data

    def get(self, employee_id: str) -> dict[str, Any]:
        """One employee's record, or raise a message meant for a person"""
        record = self._data.get(employee_id)
        if record is None:
            raise ValueError(f"Employee '{employee_id}' not found.")
        return record

    def create(self, employee_id: str, balance: int) -> dict[str, Any]:
        """Add a new employee record"""
        self._data[employee_id] = {"balance": balance, "history": []}
        return self._data[employee_id]
