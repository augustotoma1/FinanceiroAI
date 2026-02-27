"""
Conta Azul Service v2 - Complete Financial API Integration

Integrates with Conta Azul API v2 (https://api-v2.contaazul.com)
Provides full financial management capabilities:
- Financial accounts & real-time balances
- Accounts receivable (contas a receber)
- Accounts payable (contas a pagar)
- Installments / parcelas (with rateio, centro de custo, categoria)
- Payment settlement (baixas / acquittance)
- Financial categories (receitas/despesas)
- DRE categories (Demonstração do Resultado do Exercício)
- Cost centers (centros de custo)
- Sales (vendas) with PDF generation
- Customers & suppliers CRUD
- Products & services CRUD

OAuth 2.0 authentication with automatic token refresh.
Rate limit: 600 req/min, 10 req/sec per connected account.
"""

import logging
import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone, timedelta
import httpx

logger = logging.getLogger(__name__)

# ─── API v2 Base URLs ──────────────────────────────────────────────────
API_V2_BASE = "https://api-v2.contaazul.com"
API_V1_BASE = "https://api.contaazul.com/v1"  # Legacy endpoints still in use
AUTH_URL = "https://auth.contaazul.com/oauth2/token"

# Rate limiting
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


class ContaAzulService:
    """
    Complete Conta Azul API v2 integration service.

    Usage:
        service = ContaAzulService()
        contas = await service.get_contas_financeiras(access_token="...")
        saldo = await service.get_saldo_conta(access_token, conta_id)
    """

    def __init__(self, base_url: str = None):
        self.base_url_v2 = base_url or API_V2_BASE
        self.base_url_v1 = API_V1_BASE
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    # ─── HTTP Helper ─────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        url: str,
        access_token: str,
        params: dict = None,
        json_data: dict = None,
        retries: int = MAX_RETRIES
    ) -> Optional[Any]:
        """Make authenticated HTTP request with retry logic."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                        json=json_data,
                    )

                    if response.status_code == 429:
                        # Rate limited - wait and retry
                        wait = RETRY_DELAY * (2 ** attempt)
                        logger.warning(f"Rate limited. Waiting {wait}s (attempt {attempt + 1})")
                        await asyncio.sleep(wait)
                        continue

                    if response.status_code == 204:
                        return {}

                    if response.status_code >= 400:
                        error_body = response.text[:500]
                        logger.error(
                            f"Conta Azul API error {response.status_code}: "
                            f"{method} {url} -> {error_body}"
                        )
                        if response.status_code == 401:
                            return None  # Token expired
                        if response.status_code >= 500 and attempt < retries - 1:
                            await asyncio.sleep(RETRY_DELAY)
                            continue
                        return None

                    return response.json()

            except httpx.TimeoutException:
                logger.warning(f"Timeout on {method} {url} (attempt {attempt + 1})")
                if attempt < retries - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                return None
            except Exception as e:
                logger.error(f"Request error: {method} {url} -> {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                return None

        return None

    async def _get(self, path: str, access_token: str, params: dict = None, use_v2: bool = True) -> Optional[Any]:
        base = self.base_url_v2 if use_v2 else self.base_url_v1
        url = f"{base}{path}"
        return await self._request("GET", url, access_token, params=params)

    async def _post(self, path: str, access_token: str, json_data: dict = None, use_v2: bool = True) -> Optional[Any]:
        base = self.base_url_v2 if use_v2 else self.base_url_v1
        url = f"{base}{path}"
        return await self._request("POST", url, access_token, json_data=json_data)

    async def _patch(self, path: str, access_token: str, json_data: dict = None, use_v2: bool = True) -> Optional[Any]:
        base = self.base_url_v2 if use_v2 else self.base_url_v1
        url = f"{base}{path}"
        return await self._request("PATCH", url, access_token, json_data=json_data)

    async def _delete(self, path: str, access_token: str, use_v2: bool = True) -> Optional[Any]:
        base = self.base_url_v2 if use_v2 else self.base_url_v1
        url = f"{base}{path}"
        return await self._request("DELETE", url, access_token)

    # ═══════════════════════════════════════════════════════════════════
    # 1. CONTAS FINANCEIRAS (Financial Accounts)
    # ═══════════════════════════════════════════════════════════════════

    async def get_contas_financeiras(
        self,
        access_token: str,
        tipo: str = None,
        ativo: bool = None
    ) -> Optional[List[Dict]]:
        """
        List all financial accounts (bank accounts, cash, cards, etc.)

        Args:
            tipo: Filter by type (CONTA_CORRENTE, POUPANCA, CAIXINHA,
                  CARTAO_CREDITO, INVESTIMENTO, APLICACAO, MEIOS_RECEBIMENTO,
                  COBRANCAS_CONTA_AZUL, RECEBA_FACIL_CARTAO, OUTROS)
            ativo: Filter by active status

        Returns: List of financial account objects
        """
        params = {}
        if tipo:
            params["tipo"] = tipo
        if ativo is not None:
            params["ativo"] = str(ativo).lower()

        result = await self._get("/v1/conta-financeira", access_token, params=params)

        # Fallback to legacy API if v2 fails
        if result is None:
            logger.info("Trying legacy API for contas financeiras...")
            result = await self._get("/v1/bank/account", access_token, use_v2=False)

        if isinstance(result, dict) and "data" in result:
            return result["data"]
        if isinstance(result, list):
            return result
        return result

    async def get_saldo_conta(
        self,
        access_token: str,
        conta_id: str
    ) -> Optional[Dict]:
        """
        Get real-time balance for a specific financial account.

        NEW in API v2: Provides real-time balance instead of cached values.

        Args:
            conta_id: Financial account UUID

        Returns: {"saldo": float, "data_saldo": "YYYY-MM-DD", ...}
        """
        result = await self._get(
            f"/v1/conta-financeira/{conta_id}/saldo-atual",
            access_token
        )

        # Fallback
        if result is None:
            result = await self._get(
                f"/v1/bank/account/{conta_id}/balance",
                access_token,
                use_v2=False
            )

        return result

    async def get_saldos_todas_contas(self, access_token: str) -> List[Dict]:
        """
        Get real-time balances for ALL active accounts.
        Fetches account list then queries each balance individually.

        Returns: List of {nome, tipo, saldo, conta_id} dicts
        """
        contas = await self.get_contas_financeiras(access_token, ativo=True)
        if not contas:
            return []

        resultados = []
        for conta in contas:
            conta_id = conta.get("id")
            nome = conta.get("nome", "") or conta.get("descricao", "") or "Sem nome"
            tipo = (conta.get("tipo", "") or "OUTROS").upper()
            saldo_cached = float(conta.get("saldo", 0) or conta.get("saldo_atual", 0) or 0)

            saldo_real = saldo_cached
            if conta_id:
                try:
                    saldo_data = await self.get_saldo_conta(access_token, str(conta_id))
                    if saldo_data:
                        saldo_real = float(
                            saldo_data.get("saldo", 0) or
                            saldo_data.get("valor", 0) or
                            saldo_data.get("balance", 0) or 0
                        )
                except Exception:
                    pass

            resultados.append({
                "id": conta_id,
                "nome": nome,
                "tipo": tipo,
                "saldo": saldo_real,
                "ativo": conta.get("ativo", True),
            })

        return resultados

    # ═══════════════════════════════════════════════════════════════════
    # 2. CONTAS A RECEBER (Accounts Receivable)
    # ═══════════════════════════════════════════════════════════════════

    async def get_contas_receber(
        self,
        access_token: str,
        data_vencimento_de: str = None,
        data_vencimento_ate: str = None,
        status: str = None,
        cliente_id: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Optional[List[Dict]]:
        """
        Search accounts receivable with filters.

        Args:
            data_vencimento_de: Start date (YYYY-MM-DD)
            data_vencimento_ate: End date (YYYY-MM-DD)
            status: PENDING, OVERDUE, ACQUITTED, LOST, etc.
            cliente_id: Filter by customer UUID
            limit: Max results (default 50)
            offset: Pagination offset

        Returns: List of receivable event objects
        """
        params = {"limit": limit, "offset": offset}
        if data_vencimento_de:
            params["data_vencimento_de"] = data_vencimento_de
        if data_vencimento_ate:
            params["data_vencimento_ate"] = data_vencimento_ate
        if status:
            params["status"] = status
        if cliente_id:
            params["cliente_id"] = cliente_id

        result = await self._get(
            "/v1/financeiro/eventos-financeiros/contas-a-receber/buscar",
            access_token,
            params=params
        )

        # Fallback to legacy
        if result is None:
            params_legacy = {"size": limit}
            if data_vencimento_de:
                params_legacy["date_start"] = data_vencimento_de
            if data_vencimento_ate:
                params_legacy["date_end"] = data_vencimento_ate
            result = await self._get(
                "/v1/finance/receivable",
                access_token,
                params=params_legacy,
                use_v2=False
            )

        if isinstance(result, dict) and "data" in result:
            return result["data"]
        if isinstance(result, list):
            return result
        return result

    async def criar_conta_receber(
        self,
        access_token: str,
        dados: Dict
    ) -> Optional[Dict]:
        """
        Create a new accounts receivable event.

        Args:
            dados: {
                "descricao": "Consultoria Janeiro",
                "cliente": {"id": "uuid"},
                "data_emissao": "2025-01-01",
                "data_vencimento": "2025-02-01",
                "total": 2000.00,
                "categoria": {"id": "uuid"},
                "conta_financeira": {"id": "uuid"},
                "forma_pagamento": "BOLETO_BANCARIO",  # or PIX, TRANSFERENCIA, etc.
                "parcelas": [{"data_vencimento": "2025-02-01", "valor": 2000.00}]
            }
        """
        return await self._post(
            "/v1/financeiro/eventos-financeiros/contas-a-receber",
            access_token,
            json_data=dados
        )

    # ═══════════════════════════════════════════════════════════════════
    # 3. CONTAS A PAGAR (Accounts Payable)
    # ═══════════════════════════════════════════════════════════════════

    async def get_contas_pagar(
        self,
        access_token: str,
        data_vencimento_de: str = None,
        data_vencimento_ate: str = None,
        status: str = None,
        fornecedor_id: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Optional[List[Dict]]:
        """
        Search accounts payable with filters.

        Args:
            data_vencimento_de: Start date (YYYY-MM-DD)
            data_vencimento_ate: End date (YYYY-MM-DD)
            status: PENDING, OVERDUE, ACQUITTED, etc.
            fornecedor_id: Filter by supplier UUID
            limit: Max results
            offset: Pagination offset

        Returns: List of payable event objects
        """
        params = {"limit": limit, "offset": offset}
        if data_vencimento_de:
            params["data_vencimento_de"] = data_vencimento_de
        if data_vencimento_ate:
            params["data_vencimento_ate"] = data_vencimento_ate
        if status:
            params["status"] = status
        if fornecedor_id:
            params["fornecedor_id"] = fornecedor_id

        result = await self._get(
            "/v1/financeiro/eventos-financeiros/contas-a-pagar/buscar",
            access_token,
            params=params
        )

        # Fallback
        if result is None:
            params_legacy = {"size": limit}
            if data_vencimento_de:
                params_legacy["date_start"] = data_vencimento_de
            if data_vencimento_ate:
                params_legacy["date_end"] = data_vencimento_ate
            result = await self._get(
                "/v1/finance/payable",
                access_token,
                params=params_legacy,
                use_v2=False
            )

        if isinstance(result, dict) and "data" in result:
            return result["data"]
        if isinstance(result, list):
            return result
        return result

    async def criar_conta_pagar(
        self,
        access_token: str,
        dados: Dict
    ) -> Optional[Dict]:
        """
        Create a new accounts payable event.

        Args:
            dados: {
                "descricao": "Aluguel Escritório",
                "fornecedor": {"id": "uuid"},
                "data_emissao": "2025-01-01",
                "data_vencimento": "2025-01-10",
                "total": 3000.00,
                "categoria": {"id": "uuid"},
                "conta_financeira": {"id": "uuid"},
                "centro_custo": {"id": "uuid"},
                "forma_pagamento": "TRANSFERENCIA",
                "parcelas": [{"data_vencimento": "2025-01-10", "valor": 3000.00}]
            }
        """
        return await self._post(
            "/v1/financeiro/eventos-financeiros/contas-a-pagar",
            access_token,
            json_data=dados
        )

    # ═══════════════════════════════════════════════════════════════════
    # 4. PARCELAS (Installments)
    # ═══════════════════════════════════════════════════════════════════

    async def get_parcelas_evento(
        self,
        access_token: str,
        evento_id: str
    ) -> Optional[List[Dict]]:
        """
        List installments of a financial event.

        Returns parcelas with rateio, centro de custo, and categoria details.
        """
        result = await self._get(
            f"/v1/financeiro/eventos-financeiros/{evento_id}/parcelas",
            access_token
        )
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        if isinstance(result, list):
            return result
        return result

    async def get_parcela_detalhe(
        self,
        access_token: str,
        parcela_id: str
    ) -> Optional[Dict]:
        """
        Get detailed installment info including rateio, cost center, category.
        """
        return await self._get(
            f"/v1/financeiro/eventos-financeiros/parcelas/{parcela_id}",
            access_token
        )

    async def atualizar_parcela(
        self,
        access_token: str,
        parcela_id: str,
        dados: Dict
    ) -> Optional[Dict]:
        """
        Update installment (e.g., change due date, amount).

        Args:
            parcela_id: Installment UUID
            dados: Fields to update
        """
        return await self._patch(
            f"/v1/financeiro/eventos-financeiros/parcelas/{parcela_id}",
            access_token,
            json_data=dados
        )

    # ═══════════════════════════════════════════════════════════════════
    # 5. BAIXAS (Payment Settlement / Acquittance)
    # ═══════════════════════════════════════════════════════════════════

    async def dar_baixa(
        self,
        access_token: str,
        parcela_id: str,
        dados: Dict = None
    ) -> Optional[Dict]:
        """
        Settle/acquit an installment (mark as paid).

        Args:
            parcela_id: Installment UUID
            dados: {
                "data_baixa": "2025-01-15",
                "valor": 2000.00,
                "conta_financeira": {"id": "uuid"},
                "forma_pagamento": "PIX"
            }
        """
        return await self._post(
            f"/v1/financeiro/eventos-financeiros/parcelas/{parcela_id}/baixa",
            access_token,
            json_data=dados or {}
        )

    async def get_baixas(
        self,
        access_token: str,
        parcela_id: str
    ) -> Optional[List[Dict]]:
        """Get settlement history for an installment."""
        result = await self._get(
            f"/v1/financeiro/eventos-financeiros/parcelas/{parcela_id}/baixa",
            access_token
        )
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        return result

    # ═══════════════════════════════════════════════════════════════════
    # 6. CATEGORIAS FINANCEIRAS (Financial Categories)
    # ═══════════════════════════════════════════════════════════════════

    async def get_categorias(
        self,
        access_token: str,
        tipo: str = None,
        nome: str = None
    ) -> Optional[List[Dict]]:
        """
        List financial categories for classification.

        Args:
            tipo: "RECEITA" or "DESPESA"
            nome: Filter by name (partial match)

        Returns: List of {id, nome, tipo, ativo, ...}
        """
        params = {}
        if tipo:
            params["tipo"] = tipo
        if nome:
            params["nome"] = nome

        result = await self._get("/v1/categorias", access_token, params=params)

        # Fallback
        if result is None:
            result = await self._get(
                "/v1/finance/category",
                access_token,
                use_v2=False
            )

        if isinstance(result, dict) and "data" in result:
            return result["data"]
        if isinstance(result, list):
            return result
        return result

    async def get_categorias_dre(self, access_token: str) -> Optional[Dict]:
        """
        Get DRE (Demonstração do Resultado do Exercício) category structure.

        Returns hierarchical structure:
        {
            "receitas": [
                {"nome": "Receita Operacional", "subcategorias": [...]},
                ...
            ],
            "despesas": [
                {"nome": "Custos", "subcategorias": [...]},
                {"nome": "Despesas Operacionais", "subcategorias": [...]},
                ...
            ]
        }
        """
        result = await self._get("/v1/financeiro/categorias-dre", access_token)
        return result

    # ═══════════════════════════════════════════════════════════════════
    # 7. CENTROS DE CUSTO (Cost Centers)
    # ═══════════════════════════════════════════════════════════════════

    async def get_centros_custo(
        self,
        access_token: str,
        nome: str = None
    ) -> Optional[List[Dict]]:
        """
        List cost centers.

        Args:
            nome: Filter by name

        Returns: List of {id, nome, ativo, ...}
        """
        params = {}
        if nome:
            params["nome"] = nome

        result = await self._get("/v1/centro-de-custo", access_token, params=params)

        # Fallback
        if result is None:
            result = await self._get(
                "/v1/finance/costcentre",
                access_token,
                use_v2=False
            )

        if isinstance(result, dict) and "data" in result:
            return result["data"]
        if isinstance(result, list):
            return result
        return result

    async def criar_centro_custo(
        self,
        access_token: str,
        nome: str
    ) -> Optional[Dict]:
        """Create a new cost center."""
        return await self._post(
            "/v1/centro-de-custo",
            access_token,
            json_data={"nome": nome}
        )

    # ═══════════════════════════════════════════════════════════════════
    # 8. VENDAS (Sales)
    # ═══════════════════════════════════════════════════════════════════

    async def get_vendas(
        self,
        access_token: str,
        data_de: str = None,
        data_ate: str = None,
        status: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Optional[List[Dict]]:
        """
        Search sales with filters.

        Args:
            data_de: Start date (YYYY-MM-DD)
            data_ate: End date (YYYY-MM-DD)
            status: EMITIDA, CANCELADA, etc.
            limit: Max results
        """
        params = {"limit": limit, "offset": offset}
        if data_de:
            params["data_de"] = data_de
        if data_ate:
            params["data_ate"] = data_ate
        if status:
            params["status"] = status

        result = await self._get("/v1/venda/busca", access_token, params=params)

        if isinstance(result, dict) and "data" in result:
            return result["data"]
        if isinstance(result, list):
            return result
        return result

    async def get_venda_detalhe(
        self,
        access_token: str,
        venda_id: str
    ) -> Optional[Dict]:
        """Get detailed sale information."""
        return await self._get(f"/v1/venda/{venda_id}", access_token)

    async def criar_venda(
        self,
        access_token: str,
        dados: Dict
    ) -> Optional[Dict]:
        """
        Create a new sale.

        Args:
            dados: {
                "cliente": {"id": "uuid"},
                "data_emissao": "2025-01-01",
                "forma_pagamento": "BOLETO_BANCARIO",
                "itens": [
                    {"produto": {"id": "uuid"}, "quantidade": 1, "valor_unitario": 1000.00}
                ],
                "evento_financeiro": {
                    "data_vencimento": "2025-02-01",
                    "categoria": {"id": "uuid"},
                    "conta_financeira": {"id": "uuid"}
                }
            }
        """
        return await self._post("/v1/venda", access_token, json_data=dados)

    async def get_venda_pdf(
        self,
        access_token: str,
        venda_id: str
    ) -> Optional[bytes]:
        """
        Generate PDF for a sale.
        Returns PDF bytes that can be sent via Telegram.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/pdf",
        }
        url = f"{self.base_url_v2}/v1/venda/{venda_id}/pdf"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.content
                logger.error(f"Error getting sale PDF: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error getting sale PDF: {e}")
            return None

    async def get_vendedores(self, access_token: str) -> Optional[List[Dict]]:
        """List all registered sellers."""
        result = await self._get("/v1/venda/vendedores", access_token)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        return result

    # ═══════════════════════════════════════════════════════════════════
    # 9. CLIENTES E FORNECEDORES (Customers & Suppliers)
    # ═══════════════════════════════════════════════════════════════════

    async def get_clientes(
        self,
        access_token: str,
        nome: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> Optional[List[Dict]]:
        """List customers with optional name filter."""
        params = {"size": limit, "offset": offset}
        if nome:
            params["search"] = nome

        # Try v2 first, then legacy
        result = await self._get("/v1/pessoa/busca", access_token, params={**params, "tipo": "CLIENTE"})
        if result is None:
            result = await self._get(
                "/v1/contacts",
                access_token,
                params={**params, "type": "CUSTOMER"},
                use_v2=False
            )

        if isinstance(result, dict) and "data" in result:
            return result["data"]
        if isinstance(result, list):
            return result
        return result

    async def get_fornecedores(
        self,
        access_token: str,
        nome: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> Optional[List[Dict]]:
        """List suppliers with optional name filter."""
        params = {"size": limit, "offset": offset}
        if nome:
            params["search"] = nome

        result = await self._get("/v1/pessoa/busca", access_token, params={**params, "tipo": "FORNECEDOR"})
        if result is None:
            result = await self._get(
                "/v1/contacts",
                access_token,
                params={**params, "type": "VENDOR"},
                use_v2=False
            )

        if isinstance(result, dict) and "data" in result:
            return result["data"]
        if isinstance(result, list):
            return result
        return result

    async def criar_cliente(
        self,
        access_token: str,
        dados: Dict
    ) -> Optional[Dict]:
        """
        Create a new customer.

        Args:
            dados: {
                "nome": "Empresa XYZ",
                "cnpj": "12345678000190",  # or cpf
                "email": "contato@xyz.com",
                "telefone": "(11) 99999-9999",
                "endereco": {...}
            }
        """
        return await self._post("/v1/pessoa", access_token, json_data={**dados, "tipo": "CLIENTE"})

    async def criar_fornecedor(
        self,
        access_token: str,
        dados: Dict
    ) -> Optional[Dict]:
        """Create a new supplier."""
        return await self._post("/v1/pessoa", access_token, json_data={**dados, "tipo": "FORNECEDOR"})

    # ═══════════════════════════════════════════════════════════════════
    # 10. PRODUTOS E SERVICOS (Products & Services)
    # ═══════════════════════════════════════════════════════════════════

    async def get_produtos(
        self,
        access_token: str,
        nome: str = None,
        limit: int = 50
    ) -> Optional[List[Dict]]:
        """List products with optional name filter."""
        params = {"size": limit}
        if nome:
            params["search"] = nome

        result = await self._get("/v1/produto/busca", access_token, params=params)
        if result is None:
            result = await self._get(
                "/v1/products",
                access_token,
                params=params,
                use_v2=False
            )

        if isinstance(result, dict) and "data" in result:
            return result["data"]
        if isinstance(result, list):
            return result
        return result

    async def get_servicos(
        self,
        access_token: str,
        nome: str = None,
        limit: int = 50
    ) -> Optional[List[Dict]]:
        """List services with optional name filter."""
        params = {"size": limit}
        if nome:
            params["search"] = nome

        result = await self._get("/v1/servico/busca", access_token, params=params)
        if result is None:
            result = await self._get(
                "/v1/services",
                access_token,
                params=params,
                use_v2=False
            )

        if isinstance(result, dict) and "data" in result:
            return result["data"]
        if isinstance(result, list):
            return result
        return result

    # ═══════════════════════════════════════════════════════════════════
    # 11. HIGH-LEVEL ANALYTICS (Computed summaries)
    # ═══════════════════════════════════════════════════════════════════

    async def get_fluxo_caixa_resumo(
        self,
        access_token: str,
        periodo_dias: int = 30
    ) -> Dict:
        """
        Generate a cash flow summary for the given period.

        Combines:
        - Current balances (saldos)
        - Accounts receivable (upcoming + overdue)
        - Accounts payable (upcoming + overdue)

        Returns comprehensive cash flow analysis.
        """
        agora = datetime.now(timezone.utc)
        hoje = agora.strftime("%Y-%m-%d")
        de = (agora - timedelta(days=periodo_dias)).strftime("%Y-%m-%d")
        ate = (agora + timedelta(days=periodo_dias)).strftime("%Y-%m-%d")

        resultado = {
            "data_consulta": hoje,
            "periodo": f"{de} a {ate}",
            "saldos": [],
            "total_saldos": 0.0,
            "receber_pendente": 0.0,
            "receber_atrasado": 0.0,
            "receber_total_parcelas": 0,
            "pagar_pendente": 0.0,
            "pagar_atrasado": 0.0,
            "pagar_total_parcelas": 0,
            "projecao_liquida": 0.0,
            "inadimplentes": [],
            "vencimentos_proximos": [],
        }

        # 1. Saldos atuais
        try:
            saldos = await self.get_saldos_todas_contas(access_token)
            resultado["saldos"] = saldos
            resultado["total_saldos"] = sum(s["saldo"] for s in saldos)
        except Exception as e:
            logger.error(f"Erro ao buscar saldos: {e}")

        # 2. Contas a receber
        try:
            receber = await self.get_contas_receber(
                access_token, data_vencimento_de=de, data_vencimento_ate=ate, limit=100
            )
            if receber:
                for c in receber:
                    status = (c.get("status", "") or "").upper()
                    if status in ("ACQUITTED", "QUITADO", "PAGO", "RECEBIDO", "CANCELADO", "LOST", "PERDIDO"):
                        continue
                    valor = float(c.get("nao_pago", 0) or c.get("total", 0) or 0)
                    venc = (c.get("data_vencimento", "") or "")[:10]
                    resultado["receber_total_parcelas"] += 1

                    cliente_obj = c.get("cliente") or {}
                    nome_cliente = cliente_obj.get("nome", "") if isinstance(cliente_obj, dict) else ""
                    if not nome_cliente:
                        nome_cliente = c.get("descricao", "") or "N/A"

                    if venc < hoje:
                        resultado["receber_atrasado"] += valor
                        resultado["inadimplentes"].append({
                            "nome": nome_cliente,
                            "valor": valor,
                            "vencimento": venc,
                            "dias_atraso": (agora - datetime.strptime(venc, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days
                        })
                    else:
                        resultado["receber_pendente"] += valor
                        resultado["vencimentos_proximos"].append({
                            "tipo": "RECEBER",
                            "nome": nome_cliente,
                            "valor": valor,
                            "vencimento": venc,
                        })
        except Exception as e:
            logger.error(f"Erro ao buscar contas a receber: {e}")

        # 3. Contas a pagar
        try:
            pagar = await self.get_contas_pagar(
                access_token, data_vencimento_de=de, data_vencimento_ate=ate, limit=100
            )
            if pagar:
                for c in pagar:
                    status = (c.get("status", "") or "").upper()
                    if status in ("ACQUITTED", "QUITADO", "PAGO", "CANCELADO", "LOST", "PERDIDO"):
                        continue
                    valor = float(c.get("nao_pago", 0) or c.get("total", 0) or 0)
                    venc = (c.get("data_vencimento", "") or "")[:10]
                    resultado["pagar_total_parcelas"] += 1

                    fornecedor_obj = c.get("fornecedor") or c.get("cliente") or {}
                    nome_forn = fornecedor_obj.get("nome", "") if isinstance(fornecedor_obj, dict) else ""
                    if not nome_forn:
                        nome_forn = c.get("descricao", "") or "N/A"

                    if venc < hoje:
                        resultado["pagar_atrasado"] += valor
                    else:
                        resultado["pagar_pendente"] += valor
                        resultado["vencimentos_proximos"].append({
                            "tipo": "PAGAR",
                            "nome": nome_forn,
                            "valor": valor,
                            "vencimento": venc,
                        })
        except Exception as e:
            logger.error(f"Erro ao buscar contas a pagar: {e}")

        # 4. Projeção líquida
        resultado["projecao_liquida"] = (
            resultado["total_saldos"]
            + resultado["receber_pendente"]
            - resultado["pagar_pendente"]
        )

        # Sort
        resultado["inadimplentes"].sort(key=lambda x: x.get("dias_atraso", 0), reverse=True)
        resultado["vencimentos_proximos"].sort(key=lambda x: x.get("vencimento", ""))

        return resultado

    async def get_resumo_financeiro_completo(
        self,
        access_token: str
    ) -> str:
        """
        Generate a complete text-based financial summary for AI context.
        Enhanced version with all new API v2 data.

        Returns formatted text suitable for system prompt injection.
        """
        agora = datetime.now(timezone.utc)
        hoje = agora.strftime("%Y-%m-%d")
        de = (agora - timedelta(days=365)).strftime("%Y-%m-%d")
        ate = (agora + timedelta(days=90)).strftime("%Y-%m-%d")

        parts = []

        # 1. Saldos em tempo real
        try:
            saldos = await self.get_saldos_todas_contas(access_token)
            if saldos:
                total = sum(s["saldo"] for s in saldos)
                contas_txt = "; ".join(
                    f"{s['nome']}: R$ {s['saldo']:,.2f}" for s in saldos if s.get("ativo", True)
                )
                parts.append(
                    f"SALDOS BANCARIOS (TEMPO REAL): Total R$ {total:,.2f} em {len(saldos)} contas. {contas_txt}"
                )
        except Exception as e:
            parts.append(f"Saldos: erro ({str(e)[:50]})")

        # 2. Contas a receber
        try:
            receber = await self.get_contas_receber(
                access_token, data_vencimento_de=de, data_vencimento_ate=ate, limit=50
            )
            if receber:
                pendente_r = atrasado_r = quitado_r = 0
                n_pendentes = n_atrasadas = n_quitadas = 0
                inadimplentes = []
                for c in receber:
                    status = (c.get("status", "") or "").upper()
                    valor = float(c.get("nao_pago", 0) or c.get("total", 0) or 0)
                    venc = (c.get("data_vencimento", "") or "")[:10]
                    if status in ("ACQUITTED", "QUITADO", "PAGO", "RECEBIDO"):
                        n_quitadas += 1
                        quitado_r += float(c.get("total", 0) or 0)
                        continue
                    if status in ("LOST", "PERDIDO", "CANCELADO"):
                        continue
                    cliente_obj = c.get("cliente") or {}
                    nome = cliente_obj.get("nome", "") if isinstance(cliente_obj, dict) else c.get("descricao", "N/A")
                    if venc and venc < hoje:
                        atrasado_r += valor
                        n_atrasadas += 1
                        inadimplentes.append(f"{nome[:20]}: R$ {valor:,.2f} venc {venc}")
                    else:
                        pendente_r += valor
                        n_pendentes += 1

                txt = (
                    f"CONTAS A RECEBER: {n_pendentes} pendentes (R$ {pendente_r:,.2f}), "
                    f"{n_atrasadas} atrasadas (R$ {atrasado_r:,.2f}), "
                    f"{n_quitadas} quitadas (R$ {quitado_r:,.2f})"
                )
                if inadimplentes:
                    txt += "\n  Inadimplentes: " + "; ".join(inadimplentes[:8])
                parts.append(txt)
        except Exception as e:
            parts.append(f"Contas a receber: erro ({str(e)[:50]})")

        # 3. Contas a pagar
        try:
            pagar = await self.get_contas_pagar(
                access_token, data_vencimento_de=de, data_vencimento_ate=ate, limit=50
            )
            if pagar:
                pendente_p = atrasado_p = pago_p = 0
                n_pendentes_p = n_atrasadas_p = n_pagas = 0
                atrasados_forn = []
                for c in pagar:
                    status = (c.get("status", "") or "").upper()
                    valor = float(c.get("nao_pago", 0) or c.get("total", 0) or 0)
                    venc = (c.get("data_vencimento", "") or "")[:10]
                    if status in ("ACQUITTED", "QUITADO", "PAGO"):
                        n_pagas += 1
                        pago_p += float(c.get("total", 0) or 0)
                        continue
                    if status in ("LOST", "PERDIDO", "CANCELADO"):
                        continue
                    forn_obj = c.get("fornecedor") or c.get("cliente") or {}
                    nome = forn_obj.get("nome", "") if isinstance(forn_obj, dict) else c.get("descricao", "N/A")
                    if venc and venc < hoje:
                        atrasado_p += valor
                        n_atrasadas_p += 1
                        atrasados_forn.append(f"{nome[:20]}: R$ {valor:,.2f} venc {venc}")
                    else:
                        pendente_p += valor
                        n_pendentes_p += 1

                txt = (
                    f"CONTAS A PAGAR: {n_pendentes_p} pendentes (R$ {pendente_p:,.2f}), "
                    f"{n_atrasadas_p} atrasadas (R$ {atrasado_p:,.2f}), "
                    f"{n_pagas} pagas (R$ {pago_p:,.2f})"
                )
                if atrasados_forn:
                    txt += "\n  Fornecedores atrasados: " + "; ".join(atrasados_forn[:8])
                parts.append(txt)
        except Exception as e:
            parts.append(f"Contas a pagar: erro ({str(e)[:50]})")

        # 4. Categorias DRE (resumo)
        try:
            dre = await self.get_categorias_dre(access_token)
            if dre:
                n_categorias = 0
                if isinstance(dre, list):
                    n_categorias = len(dre)
                elif isinstance(dre, dict):
                    for v in dre.values():
                        if isinstance(v, list):
                            n_categorias += len(v)
                parts.append(f"CATEGORIAS DRE: {n_categorias} categorias configuradas")
        except Exception:
            pass

        # 5. Centros de custo
        try:
            centros = await self.get_centros_custo(access_token)
            if centros:
                nomes = [c.get("nome", "") for c in centros[:10] if c.get("ativo", True)]
                parts.append(f"CENTROS DE CUSTO: {', '.join(nomes)}")
        except Exception:
            pass

        return "\n".join(parts) if parts else "Sem dados financeiros disponiveis."

    # ═══════════════════════════════════════════════════════════════════
    # 12. OAuth Token Management
    # ═══════════════════════════════════════════════════════════════════

    async def refresh_token(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str
    ) -> Optional[Dict]:
        """
        Refresh OAuth 2.0 access token.

        Returns: {access_token, refresh_token, expires_in, token_type}
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    AUTH_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                if response.status_code == 200:
                    return response.json()
                logger.error(f"Token refresh failed: {response.status_code} {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return None

    async def exchange_code(
        self,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str
    ) -> Optional[Dict]:
        """
        Exchange authorization code for access token.

        Returns: {access_token, refresh_token, expires_in, token_type}
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    AUTH_URL,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                if response.status_code == 200:
                    return response.json()
                logger.error(f"Code exchange failed: {response.status_code} {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Code exchange error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════
    # 13. SYNC HELPERS (for Telegram bot)
    # ═══════════════════════════════════════════════════════════════════

    async def sync_clientes_to_db(self, access_token: str, db_session) -> int:
        """
        Sync customers from Conta Azul to local database.
        Returns number of synced clients.
        """
        from app.models.client import Client

        clientes = await self.get_clientes(access_token, limit=200)
        if not clientes:
            return 0

        count = 0
        for c in clientes:
            nome = c.get("nome") or c.get("name") or ""
            email = c.get("email") or ""
            cnpj = c.get("cnpj") or c.get("cpf") or c.get("document") or ""
            telefone = c.get("telefone") or c.get("phone") or ""
            ca_id = str(c.get("id", ""))

            if not nome:
                continue

            existing = db_session.query(Client).filter_by(conta_azul_id=ca_id).first() if ca_id else None
            if not existing:
                existing = db_session.query(Client).filter_by(email=email).first() if email else None

            if existing:
                existing.name = nome
                if email:
                    existing.email = email
                if cnpj:
                    existing.document = cnpj
                if telefone:
                    existing.phone = telefone
                existing.conta_azul_id = ca_id
            else:
                new_client = Client(
                    name=nome,
                    email=email,
                    document=cnpj,
                    phone=telefone,
                    conta_azul_id=ca_id,
                    status="active"
                )
                db_session.add(new_client)
            count += 1

        db_session.commit()
        return count
