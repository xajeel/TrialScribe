"""Current organization-membership verification through user-service."""

from uuid import UUID

import httpx

from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.utils.constant import (
    AUTHORIZATION_HEADER,
    REQUEST_ID_HEADER,
)
from trialscribe_gateway.utils.exceptions import (
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)


class OrganizationAccessService:
    """Ask user-service whether the current token can see an organization."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: GatewaySettings,
    ) -> None:
        self._client = client
        self._settings = settings

    async def membership_status(
        self,
        bearer_token: str,
        organization_id: UUID,
        request_id: UUID,
    ) -> int:
        url = (
            f"{self._settings.service_url('user')}"
            f"/v1/organizations/{organization_id}"
        )
        try:
            response = await self._client.get(
                url,
                headers={
                    AUTHORIZATION_HEADER: f"Bearer {bearer_token}",
                    REQUEST_ID_HEADER: str(request_id),
                },
            )
        except httpx.TimeoutException:
            raise UpstreamTimeoutError from None
        except httpx.RequestError:
            raise UpstreamUnavailableError from None
        if response.status_code >= 500:
            raise UpstreamUnavailableError
        return response.status_code
