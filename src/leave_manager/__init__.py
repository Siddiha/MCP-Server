"""LeaveManager: an MCP server for employee leave.

The package is split so each piece has one job:

    config.py    settings read from the environment
    models.py    the shapes tools return
    storage.py   reading and writing the JSON data file
    service.py   the leave rules
    server.py    the MCP layer
"""
__version__ = "0.2.0"
