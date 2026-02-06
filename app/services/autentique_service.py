"""
Autentique API Service Client

This module provides a service client for interacting with Autentique's GraphQL API
for electronic signature platform integration.

The service handles:
- GraphQL queries and mutations for document operations
- Rate limiting enforcement (60 requests per minute)
- Bearer token authentication
- Document creation and signature tracking
- Webhook integration for status updates

Autentique API provides legally-valid electronic signatures compliant with
ICP-Brasil standards for Brazilian legal requirements.

Usage:
    from app.services.autentique_service import AutentiqueService

    service = AutentiqueService()

    # Create a document for signature
    document = await service.create_document(
        name="Service Contract",
        file_url="https://example.com/contract.pdf",
        signers=[{"email": "client@example.com", "name": "Client Name"}]
    )

    # Check signature status
    status = await service.get_document_status(document_id="doc_123")

References:
    - https://docs.autentique.com.br/
    - GraphQL schema explorer: https://altair.autentique.com.br
"""

from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
from gql.transport.exceptions import TransportError
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import deque
import asyncio
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class AutentiqueError(Exception):
    """Base exception for Autentique API errors."""
    pass


class AutentiqueRateLimitError(AutentiqueError):
    """Exception raised when rate limit is exceeded."""
    pass


class AutentiqueAPIError(AutentiqueError):
    """Exception raised for API request errors."""
    pass


class AutentiqueService:
    """
    Service client for Autentique GraphQL API integration.

    Provides methods for creating documents, tracking signature status,
    and managing electronic signature workflows with automatic rate limiting.

    The client uses configuration from environment variables:
    - AUTENTIQUE_API_KEY: API key for bearer token authentication
    - AUTENTIQUE_API_URL: GraphQL endpoint URL (default: https://api.autentique.com.br/v2/graphql)
    - AUTENTIQUE_RATE_LIMIT: Max requests per minute (default: 60)

    Attributes:
        api_url: GraphQL endpoint URL
        api_key: Bearer token for authentication
        rate_limit: Maximum requests per minute (60)
        request_timestamps: Deque tracking recent request times for rate limiting
        client: GQL client instance for GraphQL operations
    """

    def __init__(self):
        """
        Initialize Autentique GraphQL client with rate limiting.

        Configures GraphQL transport with bearer token authentication
        and sets up rate limiting tracking.

        Raises:
            ValueError: If required configuration is missing
        """
        try:
            self.api_url = settings.AUTENTIQUE_API_URL
            self.api_key = settings.AUTENTIQUE_API_KEY
            self.rate_limit = settings.AUTENTIQUE_RATE_LIMIT

            # Rate limiting: track request timestamps in sliding window
            self.request_timestamps = deque()

            # Configure GraphQL transport with authentication
            transport = RequestsHTTPTransport(
                url=self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                verify=True,
                retries=3,
                timeout=30
            )

            # Initialize GraphQL client
            self.client = Client(
                transport=transport,
                fetch_schema_from_transport=False  # Skip schema fetch for performance
            )

            logger.info(f"Autentique API service initialized with endpoint: {self.api_url}")

        except AttributeError as e:
            logger.error(f"Missing required Autentique configuration: {e}")
            raise ValueError(
                f"Autentique API initialization failed. "
                f"Ensure AUTENTIQUE_API_KEY and AUTENTIQUE_API_URL are set: {e}"
            )

    async def _wait_for_rate_limit(self):
        """
        Enforce rate limiting using sliding window algorithm.

        Ensures no more than `rate_limit` requests are made within a 1-minute window.
        If the limit is reached, waits until the oldest request falls outside the window.

        This method is called automatically before each API request.

        Rate limit: 60 requests per minute (configurable via AUTENTIQUE_RATE_LIMIT)

        Example:
            >>> service = AutentiqueService()
            >>> await service._wait_for_rate_limit()  # Called internally
        """
        now = datetime.utcnow()
        one_minute_ago = now - timedelta(minutes=1)

        # Remove timestamps older than 1 minute from sliding window
        while self.request_timestamps and self.request_timestamps[0] < one_minute_ago:
            self.request_timestamps.popleft()

        # If we've hit the rate limit, wait until oldest request expires
        if len(self.request_timestamps) >= self.rate_limit:
            oldest_request = self.request_timestamps[0]
            wait_time = (oldest_request + timedelta(minutes=1) - now).total_seconds()

            if wait_time > 0:
                logger.warning(
                    f"Rate limit reached ({self.rate_limit} req/min). "
                    f"Waiting {wait_time:.2f} seconds..."
                )
                await asyncio.sleep(wait_time)

        # Record this request timestamp
        self.request_timestamps.append(now)

    async def create_document(
        self,
        name: str,
        file: Dict[str, str],
        signers: List[Dict[str, Any]],
        show_audit_page: bool = True
    ) -> Dict[str, Any]:
        """
        Create a new document for electronic signature.

        Submits a document to Autentique and sends signature requests to
        specified signers via email.

        Args:
            name: Document name/title
            file: File information dict with "base64" key containing base64-encoded PDF
                  Example: {"base64": "JVBERi0xLjQKJ..."}
            signers: List of signer dictionaries, each containing:
                - email: Signer's email address (required)
                - name: Signer's full name (required)
                - action: Signature action type (default: "SIGN")
                Example: [{"email": "client@example.com", "name": "John Doe"}]
            show_audit_page: Include audit trail page in final document (default: True)

        Returns:
            Dictionary containing created document information:
                - id: Document ID for status tracking
                - name: Document name
                - signatures: List of signature objects with email, status, etc.

        Raises:
            AutentiqueAPIError: If document creation fails
            AutentiqueRateLimitError: If rate limit is exceeded

        Example:
            >>> service = AutentiqueService()
            >>> document = await service.create_document(
            ...     name="Service Contract - Client ABC",
            ...     file={"base64": "JVBERi0xLjQKJ..."},
            ...     signers=[
            ...         {"email": "client@example.com", "name": "Client Name"},
            ...         {"email": "company@example.com", "name": "Company Rep"}
            ...     ]
            ... )
            >>> print(document["id"])  # Use for status tracking
        """
        await self._wait_for_rate_limit()

        # GraphQL mutation for document creation
        mutation = gql("""
            mutation CreateDocument($document: DocumentInput!) {
                createDocument(document: $document) {
                    id
                    name
                    refusable
                    sortable
                    created_at
                    signatures {
                        public_id
                        name
                        email
                        created_at
                        action
                        link {
                            short_link
                        }
                        user {
                            id
                            name
                            email
                        }
                        signed {
                            created_at
                        }
                        rejected {
                            created_at
                        }
                    }
                }
            }
        """)

        # Prepare document input
        document_input = {
            "document": {
                "name": name,
                "file": file,
                "signers": signers,
                "show_audit_page": show_audit_page
            }
        }

        try:
            logger.info(f"Creating document '{name}' with {len(signers)} signer(s)")

            result = self.client.execute(mutation, variable_values=document_input)

            created_doc = result["createDocument"]
            logger.info(f"Document created successfully with ID: {created_doc['id']}")

            return created_doc

        except TransportError as e:
            logger.error(f"GraphQL transport error during document creation: {e}")
            raise AutentiqueAPIError(f"Failed to create document: {e}")

        except Exception as e:
            logger.error(f"Unexpected error during document creation: {e}")
            raise AutentiqueAPIError(f"Unexpected error: {e}")

    async def get_document_status(self, document_id: str) -> Dict[str, Any]:
        """
        Check the signature status of a document.

        Retrieves current document information including signature status
        for all signers.

        Args:
            document_id: Document ID returned from create_document

        Returns:
            Dictionary containing document information:
                - id: Document ID
                - name: Document name
                - signatures: List of signature objects with status information
                    - public_id: Signature identifier
                    - email: Signer's email
                    - signed: Object with created_at if signed, null otherwise
                    - rejected: Object with created_at if rejected, null otherwise

        Raises:
            AutentiqueAPIError: If status check fails

        Example:
            >>> service = AutentiqueService()
            >>> status = await service.get_document_status(document_id="doc_123")
            >>> for signature in status["signatures"]:
            ...     if signature["signed"]:
            ...         print(f"{signature['email']} signed on {signature['signed']['created_at']}")
            ...     elif signature["rejected"]:
            ...         print(f"{signature['email']} rejected")
            ...     else:
            ...         print(f"{signature['email']} pending")
        """
        await self._wait_for_rate_limit()

        query = gql("""
            query GetDocument($id: ID!) {
                document(id: $id) {
                    id
                    name
                    refusable
                    sortable
                    created_at
                    files {
                        original
                        signed
                    }
                    signatures {
                        public_id
                        name
                        email
                        created_at
                        action
                        link {
                            short_link
                        }
                        signed {
                            created_at
                        }
                        rejected {
                            created_at
                            reason
                        }
                    }
                }
            }
        """)

        try:
            logger.info(f"Fetching status for document: {document_id}")

            result = self.client.execute(query, variable_values={"id": document_id})

            document = result["document"]
            logger.debug(f"Document status retrieved: {document['name']}")

            return document

        except TransportError as e:
            logger.error(f"GraphQL transport error during status check: {e}")
            raise AutentiqueAPIError(f"Failed to get document status: {e}")

        except Exception as e:
            logger.error(f"Unexpected error during status check: {e}")
            raise AutentiqueAPIError(f"Unexpected error: {e}")

    async def list_documents(
        self,
        limit: int = 10,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        List documents with pagination.

        Retrieves a paginated list of documents created with the API key.

        Args:
            limit: Number of documents per page (default: 10, max: 100)
            page: Page number to retrieve (default: 1)

        Returns:
            Dictionary containing:
                - total: Total number of documents
                - data: List of document objects
                - page: Current page number
                - limit: Documents per page

        Raises:
            AutentiqueAPIError: If listing fails

        Example:
            >>> service = AutentiqueService()
            >>> result = await service.list_documents(limit=20, page=1)
            >>> for doc in result["data"]:
            ...     print(f"{doc['name']} - Created: {doc['created_at']}")
        """
        await self._wait_for_rate_limit()

        query = gql("""
            query ListDocuments($limit: Int!, $page: Int!) {
                documents(limit: $limit, page: $page) {
                    total
                    data {
                        id
                        name
                        refusable
                        sortable
                        created_at
                        signatures {
                            public_id
                            email
                            signed {
                                created_at
                            }
                        }
                    }
                }
            }
        """)

        try:
            logger.info(f"Listing documents (page {page}, limit {limit})")

            result = self.client.execute(
                query,
                variable_values={"limit": limit, "page": page}
            )

            documents = result["documents"]
            logger.debug(f"Retrieved {len(documents['data'])} documents (total: {documents['total']})")

            return documents

        except TransportError as e:
            logger.error(f"GraphQL transport error during document listing: {e}")
            raise AutentiqueAPIError(f"Failed to list documents: {e}")

        except Exception as e:
            logger.error(f"Unexpected error during document listing: {e}")
            raise AutentiqueAPIError(f"Unexpected error: {e}")

    def is_document_fully_signed(self, document: Dict[str, Any]) -> bool:
        """
        Check if all signers have signed a document.

        Helper method to determine if document signature workflow is complete.

        Args:
            document: Document dictionary from get_document_status or create_document

        Returns:
            True if all signatures are complete, False otherwise

        Example:
            >>> service = AutentiqueService()
            >>> status = await service.get_document_status(document_id="doc_123")
            >>> if service.is_document_fully_signed(status):
            ...     print("Document fully signed!")
            ...     # Download signed document
        """
        if "signatures" not in document:
            return False

        for signature in document["signatures"]:
            # If any signature is not signed and not rejected, document is incomplete
            if not signature.get("signed") and not signature.get("rejected"):
                return False

        # All signatures are either signed or rejected
        return True

    def get_pending_signers(self, document: Dict[str, Any]) -> List[str]:
        """
        Get list of email addresses for signers who haven't signed yet.

        Args:
            document: Document dictionary from get_document_status or create_document

        Returns:
            List of email addresses for pending signers

        Example:
            >>> service = AutentiqueService()
            >>> status = await service.get_document_status(document_id="doc_123")
            >>> pending = service.get_pending_signers(status)
            >>> print(f"Waiting for signatures from: {', '.join(pending)}")
        """
        pending = []

        if "signatures" not in document:
            return pending

        for signature in document["signatures"]:
            if not signature.get("signed") and not signature.get("rejected"):
                pending.append(signature["email"])

        return pending
