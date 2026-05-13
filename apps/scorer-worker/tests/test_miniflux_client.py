import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from miniflux_client import entry_query_params  # noqa: E402


def test_entry_query_params_omits_status_for_all_entries():
    assert entry_query_params(300, "all") == {
        "limit": 300,
        "order": "published_at",
        "direction": "desc",
    }


def test_entry_query_params_keeps_specific_status():
    assert entry_query_params(50, "unread") == {
        "limit": 50,
        "order": "published_at",
        "direction": "desc",
        "status": "unread",
    }
