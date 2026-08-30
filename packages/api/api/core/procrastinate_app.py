import procrastinate

from api.core.settings import COMPUTE_DATABASE_URL

__all__ = ["app"]

app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=COMPUTE_DATABASE_URL),
    import_paths=("api.core.tasks",),
)
