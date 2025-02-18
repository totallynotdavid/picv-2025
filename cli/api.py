import asyncio
from typing import Dict, Optional

import aiohttp

from cli.constants import DEFAULT_TIMEOUTS
from cli.ui import UserInterface


class APIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *exc):
        await self.session.close()
        self.session = None

    async def check_connection(self) -> bool:
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                return response.status == 200
        except aiohttp.ClientError:
            UserInterface.show_error("No se pudo conectar al servidor")
            return False

    async def call_endpoint(
        self, endpoint: str, data: Dict, timeout: Optional[float] = None
    ) -> Dict:
        timeout = timeout or DEFAULT_TIMEOUTS.get(endpoint, 30)
        try:
            async with self.session.post(
                f"{self.base_url}/{endpoint}", json=data, timeout=timeout
            ) as response:
                if response.status != 200:
                    raise Exception(f"Error {response.status}: {await response.text()}")
                return await response.json()
        except asyncio.TimeoutError:
            raise Exception("Tiempo de espera excedido") from None
        except aiohttp.ClientError as e:
            raise Exception(f"Error de conexión: {str(e)}") from None

    async def get_job_status(self, job_id: str) -> Dict:
        try:
            async with self.session.get(
                f"{self.base_url}/job-status/{job_id}",
                timeout=DEFAULT_TIMEOUTS["status_check"],
            ) as response:
                if response.status != 200:
                    raise Exception(f"Error estado: {await response.text()}")
                return await response.json()
        except asyncio.TimeoutError:
            raise Exception("Tiempo de espera excedido consultando estado") from None

    async def download_report(self, job_id: str) -> bytes:
        try:
            async with self.session.get(
                f"{self.base_url}/job-result/{job_id}",
                timeout=DEFAULT_TIMEOUTS["report_download"],
            ) as response:
                if response.status != 200:
                    raise Exception(f"Error descarga: {await response.text()}")
                return await response.read()
        except asyncio.TimeoutError:
            raise Exception("Tiempo de espera excedido descargando informe") from None
