"""
PlayWebit Network SDK
L1 blockchain SDK for the PlayWebit public network.
Chain ID: 4968 | Currency: PLWB
"""

__version__ = "1.0.0"
__author__  = "PlayWebIT"
__license__ = "MIT"

from playweb.node   import PlayWebitNode
from playweb.client import PlayWebitClient

__all__ = [
    "PlayWebitNode",
    "PlayWebitClient",
    "__version__",
]
