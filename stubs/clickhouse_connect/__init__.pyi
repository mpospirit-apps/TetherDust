from collections.abc import Sequence
from typing import Any

class QueryResult:
    column_names: tuple[str, ...]
    result_rows: Sequence[Sequence[Any]]

class Client:
    def query(self, query: str, **kwargs: Any) -> QueryResult: ...
    def command(self, cmd: str, **kwargs: Any) -> Any: ...
    def close(self) -> None: ...

def get_client(
    *,
    host: str | None = ...,
    username: str | None = ...,
    password: str = ...,
    database: str = ...,
    port: int = ...,
    secure: bool | str = ...,
    **kwargs: Any,
) -> Client: ...
