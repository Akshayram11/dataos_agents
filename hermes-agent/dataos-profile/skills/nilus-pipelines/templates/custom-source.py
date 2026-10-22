from __future__ import annotations

import os
import urllib.parse
from typing import Any, Dict, Iterator, Optional

import nilus
from nilus import CustomSource


def _qp(q: dict, name: str) -> Optional[str]:
    return q.get(name, [None])[0]


def _rows(*, api_token: str, table: str) -> Iterator[Dict[str, Any]]:
    # fetch / paginate / yield one stable dict per record
    yield {"id": 1, "source_table": table}


@nilus.source(name="my_connector")
def my_connector_source(*, api_token: str, table: str):
    yield nilus.resource(
        lambda: _rows(api_token=api_token, table=table),
        name="orders",
        table_name="orders",
        write_disposition="replace",
    )


class MyCustomSource(CustomSource):
    def handles_incrementality(self) -> bool:
        return False

    def nilus_source(self, uri: str, table: str, **kwargs):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(uri).query)
        api_token = _qp(q, "api_token") or os.environ.get("API_TOKEN")
        if not api_token:
            raise ValueError("Missing api_token (URI query or API_TOKEN env)")
        return my_connector_source(api_token=api_token, table=table)
