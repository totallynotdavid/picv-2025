"""Print the FastAPI OpenAPI schema without starting a server."""

import json

from api.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=2))
