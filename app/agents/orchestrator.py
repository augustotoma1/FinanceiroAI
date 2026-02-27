"""
AI Employee orchestrator.

Execution modes:
- builtin: deterministic sequential flow.
- langgraph: graph-based state orchestration with explicit role nodes.
- crewai: delegated planning metadata while preserving deterministic tools/guardrails.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.agents.policies import (
    MANDATORY_CFO_APPROVAL_ABOVE_BRL,
    MAX_AUTONOMOUS_DISCOUNT_PCT,
    MAX_AUTONOMOUS_DISCOUNT_VALUE_BRL,
    MAX_AUTONOMOUS_GRACE_DAYS,
    MAX_AUTONOMOUS_INSTALLMENTS,
)
from app.agents.tools import AIEmployeeTools
from app.agents.types import AgentAction, OrchestrationResult
from app.config import settings

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _module_available(module_name: str) -> bool:
    """Best-effort dependency probe without importing heavy modules."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


class AIEmployeeOrchestrator:
    """Coordinates Cobrador, Contratos and CFO Assistant roles."""

    def __init__(
        self,
        tools: Optional[AIEmployeeTools] = None,
        *,
        requested_engine: Optional[str] = None,
    ):
        self.tools = tools or AIEmployeeTools()
        self.requested_engine = self._normalize_requested_engine(
            requested_engine or getattr(settings, "AI_EMPLOYEE_ORCHESTRATION_ENGINE", "builtin")
        )
        self.crewai_enabled = bool(getattr(settings, "AI_EMPLOYEE_CREW_ENABLED", False))
        self.crewai_execution_enabled = bool(
            getattr(settings, "AI_EMPLOYEE_CREW_EXECUTION_ENABLED", False)
        )
        self.langgraph_available = _module_available("langgraph")
        self.crewai_available = _module_available("crewai")

        self.runtime_engine = self._resolve_runtime_engine(
            self.requested_engine,
            crewai_enabled=self.crewai_enabled,
            langgraph_available=self.langgraph_available,
            crewai_available=self.crewai_available,
        )
        self.runtime_reason = self._resolve_runtime_reason(
            requested_engine=self.requested_engine,
            runtime_engine=self.runtime_engine,
        )

    @staticmethod
    def _normalize_requested_engine(value: Optional[str]) -> str:
        raw = str(value or "builtin").strip().lower()
        if raw in {"", "default"}:
            return "builtin"
        return raw

    @staticmethod
    def _resolve_runtime_engine(
        requested: str,
        *,
        crewai_enabled: bool,
        langgraph_available: bool,
        crewai_available: bool,
    ) -> str:
        if requested == "auto":
            if langgraph_available:
                return "langgraph"
            if crewai_enabled and crewai_available:
                return "crewai"
            return "builtin"

        if requested == "langgraph":
            if langgraph_available:
                return "langgraph"
            logger.warning(
                "LangGraph requested but not installed. Falling back to builtin orchestrator."
            )
            return "builtin"

        if requested == "crewai":
            if not crewai_enabled:
                logger.warning(
                    "CrewAI requested but AI_EMPLOYEE_CREW_ENABLED is false. "
                    "Falling back to builtin orchestrator."
                )
                return "builtin"
            if crewai_available:
                return "crewai"
            logger.warning(
                "CrewAI requested but not installed. Falling back to builtin orchestrator."
            )
            return "builtin"

        if requested not in {"builtin", ""}:
            logger.warning(
                "Unknown AI_EMPLOYEE_ORCHESTRATION_ENGINE='%s'. Falling back to builtin.",
                requested,
            )
        return "builtin"

    def _resolve_runtime_reason(self, *, requested_engine: str, runtime_engine: str) -> str:
        if requested_engine == "auto":
            if runtime_engine == "langgraph":
                return "auto_selected_langgraph"
            if runtime_engine == "crewai":
                return "auto_selected_crewai"
            return "auto_selected_builtin"
        if runtime_engine == requested_engine:
            return "ok"
        if requested_engine == "crewai" and not self.crewai_enabled:
            return "AI_EMPLOYEE_CREW_ENABLED is false"
        if requested_engine == "crewai" and not self.crewai_available:
            return "crewai dependency not installed"
        if requested_engine == "langgraph" and not self.langgraph_available:
            return "langgraph dependency not installed"
        if requested_engine not in {"builtin", "", "crewai", "langgraph", "auto"}:
            return "unknown orchestration engine requested"
        return "fallback_to_builtin"

    def runtime_status(self, *, requested_engine: Optional[str] = None) -> Dict[str, Any]:
        """Expose runtime and feature-gate status for diagnostics."""
        if requested_engine is None:
            resolved_requested = self.requested_engine
            resolved_runtime = self.runtime_engine
            resolved_reason = self.runtime_reason
        else:
            resolved_requested = self._normalize_requested_engine(requested_engine)
            resolved_runtime = self._resolve_runtime_engine(
                resolved_requested,
                crewai_enabled=self.crewai_enabled,
                langgraph_available=self.langgraph_available,
                crewai_available=self.crewai_available,
            )
            resolved_reason = self._resolve_runtime_reason(
                requested_engine=resolved_requested,
                runtime_engine=resolved_runtime,
            )
        return {
            "enabled": bool(getattr(settings, "AI_EMPLOYEE_ENABLED", False)),
            "dry_run": bool(getattr(settings, "AI_EMPLOYEE_DRY_RUN", True)),
            "requested_engine": resolved_requested,
            "runtime_engine": resolved_runtime,
            "runtime_reason": resolved_reason,
            "engine_degraded": resolved_requested != "auto" and resolved_runtime != resolved_requested,
            "supported_engines": ["builtin", "langgraph", "crewai", "auto"],
            "resolution_order": ["langgraph", "crewai", "builtin"],
            "langgraph_available": self.langgraph_available,
            "crewai_available": self.crewai_available,
            "crewai_enabled": self.crewai_enabled,
            "crewai_execution_enabled": self.crewai_execution_enabled,
            "email_preview_enabled": bool(getattr(settings, "AI_EMPLOYEE_ENABLE_EMAIL_PREVIEW", True)),
            "whatsapp_preview_enabled": bool(getattr(settings, "AI_EMPLOYEE_ENABLE_WHATSAPP_PREVIEW", False)),
            "daily_summary_enabled": bool(getattr(settings, "AI_EMPLOYEE_DAILY_SUMMARY_ENABLED", False)),
            "daily_schedule": (
                f"{int(getattr(settings, 'AI_EMPLOYEE_DAILY_HOUR', 8)):02d}:"
                f"{int(getattr(settings, 'AI_EMPLOYEE_DAILY_MINUTE', 20)):02d}"
            ),
        }

    async def run_daily_operations(
        self,
        *,
        trigger: str = "manual",
        force: bool = False,
        engine_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute one AI Employee cycle.
        """
        status_snapshot = self.runtime_status(requested_engine=engine_override)
        runtime_engine = str(status_snapshot.get("runtime_engine") or "builtin")

        if not bool(getattr(settings, "AI_EMPLOYEE_ENABLED", False)) and not force:
            return {
                "success": True,
                "skipped": True,
                "reason": "AI_EMPLOYEE_ENABLED is false",
                "trigger": trigger,
                "runtime_status": status_snapshot,
            }

        timeout_seconds = max(int(getattr(settings, "AI_EMPLOYEE_OPERATION_TIMEOUT_SECONDS", 120)), 15)
        dry_run = bool(getattr(settings, "AI_EMPLOYEE_DRY_RUN", True))
        started_at = _utc_now_iso()

        try:
            if runtime_engine == "langgraph":
                payload = await asyncio.wait_for(
                    self._run_langgraph_flow(dry_run=dry_run),
                    timeout=timeout_seconds,
                )
            elif runtime_engine == "crewai":
                payload = await asyncio.wait_for(
                    self._run_crewai_flow(dry_run=dry_run),
                    timeout=timeout_seconds,
                )
            else:
                payload = await asyncio.wait_for(
                    self._run_builtin_flow(dry_run=dry_run),
                    timeout=timeout_seconds,
                )
        except asyncio.TimeoutError:
            payload = OrchestrationResult(
                success=False,
                mode=runtime_engine,
                dry_run=dry_run,
                started_at=started_at,
                finished_at=_utc_now_iso(),
                errors=[f"operation_timeout>{timeout_seconds}s"],
            ).to_dict()
        except Exception as exc:
            logger.error("AI Employee orchestration failed: %s", exc, exc_info=True)
            payload = OrchestrationResult(
                success=False,
                mode=runtime_engine,
                dry_run=dry_run,
                started_at=started_at,
                finished_at=_utc_now_iso(),
                errors=[str(exc)],
            ).to_dict()

        payload["trigger"] = trigger
        payload["runtime_status"] = status_snapshot
        return payload

    async def _run_builtin_flow(self, *, dry_run: bool) -> Dict[str, Any]:
        started_at = _utc_now_iso()
        (
            cobrador_data,
            contratos_data,
            analista_data,
            actions,
            errors,
        ) = await self._execute_role_steps(dry_run=dry_run)
        return self._compose_result(
            mode="builtin",
            dry_run=dry_run,
            started_at=started_at,
            cobrador_data=cobrador_data,
            contratos_data=contratos_data,
            analista_data=analista_data,
            actions=actions,
            errors=errors,
        )

    async def _run_langgraph_flow(self, *, dry_run: bool) -> Dict[str, Any]:
        """
        LangGraph runtime with explicit role nodes.

        If LangGraph cannot execute, fallback to builtin flow.
        """
        try:
            from langgraph.graph import END, StateGraph  # type: ignore
        except Exception:
            return await self._run_builtin_flow(dry_run=dry_run)

        started_at = _utc_now_iso()
        orchestrator = self
        role_outputs: Dict[str, Dict[str, Any]] = {
            "cobrador_data": {},
            "contratos_data": {},
            "analista_data": {},
        }

        def _append_action(state: Dict[str, Any], action: AgentAction) -> List[Dict[str, Any]]:
            items = list(state.get("actions") or [])
            items.append(action.to_dict())
            return items

        def _append_error(state: Dict[str, Any], err: Optional[str]) -> List[str]:
            items = list(state.get("errors") or [])
            if err:
                items.append(err)
            return items

        def _node_dry_run(state: Dict[str, Any]) -> bool:
            value = state.get("dry_run")
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return dry_run

        def _escalation_state() -> Dict[str, Any]:
            return {
                "contratos_data": dict(role_outputs.get("contratos_data") or {}),
                "analista_data": dict(role_outputs.get("analista_data") or {}),
            }

        async def cobrador_node(state: Dict[str, Any]) -> Dict[str, Any]:
            data, action, err = await orchestrator._run_cobrador_agent(dry_run=_node_dry_run(state))
            role_outputs["cobrador_data"] = dict(data or {})
            return {
                "cobrador_data": data,
                "actions": _append_action(state, action),
                "errors": _append_error(state, err),
            }

        async def contratos_node(state: Dict[str, Any]) -> Dict[str, Any]:
            data, action, err = await orchestrator._run_contratos_agent(dry_run=_node_dry_run(state))
            role_outputs["contratos_data"] = dict(data or {})
            return {
                "contratos_data": data,
                "actions": _append_action(state, action),
                "errors": _append_error(state, err),
            }

        async def analista_node(state: Dict[str, Any]) -> Dict[str, Any]:
            data, action, err = await orchestrator._run_analista_cfo_agent(dry_run=_node_dry_run(state))
            role_outputs["analista_data"] = dict(data or {})
            return {
                "analista_data": data,
                "actions": _append_action(state, action),
                "errors": _append_error(state, err),
            }

        async def escalacao_node(state: Dict[str, Any]) -> Dict[str, Any]:
            should_escalate, reasons = orchestrator._requires_cfo_escalation(_escalation_state())
            if not should_escalate:
                return {}
            action = AgentAction(
                agent="orchestrator",
                action="escalar_para_cfo",
                details={"reasons": reasons},
            )
            await orchestrator._persist_action(action)
            return {
                "actions": _append_action(state, action),
            }

        def route_after_analista(state: Dict[str, Any]) -> str:
            _ = state
            should_escalate, _ = orchestrator._requires_cfo_escalation(_escalation_state())
            if should_escalate:
                return "escalacao"
            return "final"

        def final_node(state: Dict[str, Any]) -> Dict[str, Any]:
            action_payloads = list(state.get("actions") or [])
            actions = [orchestrator._hydrate_action(payload) for payload in action_payloads]
            should_escalate, reasons = orchestrator._requires_cfo_escalation(_escalation_state())
            execution_path = ["cobrador", "contratos", "analista_cfo"]
            if should_escalate:
                execution_path.append("escalacao")
            execution_path.append("final")
            payload = orchestrator._compose_result(
                mode="langgraph",
                dry_run=dry_run,
                started_at=started_at,
                cobrador_data=dict(role_outputs.get("cobrador_data") or {}),
                contratos_data=dict(role_outputs.get("contratos_data") or {}),
                analista_data=dict(role_outputs.get("analista_data") or {}),
                actions=actions,
                errors=list(state.get("errors") or []),
            )
            payload["graph"] = {
                "nodes": ["cobrador", "contratos", "analista_cfo", "escalacao", "final"],
                "execution": "conditional_state_graph",
                "execution_path": execution_path,
                "cfo_escalation": {
                    "required": should_escalate,
                    "reasons": reasons,
                },
            }
            return {"result": payload}

        graph = StateGraph(dict)
        graph.add_node("cobrador", cobrador_node)
        graph.add_node("contratos", contratos_node)
        graph.add_node("analista_cfo", analista_node)
        graph.add_node("escalacao", escalacao_node)
        graph.add_node("final", final_node)
        graph.set_entry_point("cobrador")
        graph.add_edge("cobrador", "contratos")
        graph.add_edge("contratos", "analista_cfo")
        graph.add_conditional_edges(
            "analista_cfo",
            route_after_analista,
            {
                "escalacao": "escalacao",
                "final": "final",
            },
        )
        graph.add_edge("escalacao", "final")
        graph.add_edge("final", END)

        compiled = graph.compile()
        out_state = await compiled.ainvoke(
            {
                "dry_run": dry_run,
                "started_at": started_at,
                "actions": [],
                "errors": [],
            }
        )
        payload = dict(out_state.get("result") or {})
        if payload:
            return payload
        return await self._run_builtin_flow(dry_run=dry_run)

    async def _run_crewai_flow(self, *, dry_run: bool) -> Dict[str, Any]:
        """
        CrewAI runtime bridge.

        This phase keeps side effects deterministic through local tools and
        guardrails while exposing a crew delegation plan for controlled rollout.

        Modes:
        - planning_only: deterministic orchestration + delegation plan metadata.
        - native: executes CrewAI kickoff (optional, feature-flagged).
        """
        if not self.crewai_enabled:
            return await self._run_builtin_flow(dry_run=dry_run)
        if not self.crewai_available:
            return await self._run_builtin_flow(dry_run=dry_run)

        started_at = _utc_now_iso()
        (
            cobrador_data,
            contratos_data,
            analista_data,
            actions,
            errors,
        ) = await self._execute_role_steps(dry_run=dry_run)
        payload = self._compose_result(
            mode="crewai",
            dry_run=dry_run,
            started_at=started_at,
            cobrador_data=cobrador_data,
            contratos_data=contratos_data,
            analista_data=analista_data,
            actions=actions,
            errors=errors,
        )
        payload["crew"] = self._build_crewai_plan(payload.get("summary") or {})
        payload["crew"]["execution_enabled"] = self.crewai_execution_enabled

        if not self.crewai_execution_enabled:
            return payload

        native_out = await self._run_crewai_native(
            summary=payload.get("summary") or {},
            dry_run=dry_run,
        )
        payload["crew"].update(native_out)

        native_runtime = str(native_out.get("runtime") or "").lower()
        native_error = str(native_out.get("error") or "").strip()
        if native_runtime not in {"native", "planning_only"} and native_error:
            payload.setdefault("errors", []).append(f"crewai_native:{native_error}")
            payload["success"] = False

        return payload

    async def _run_crewai_native(self, *, summary: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
        """
        Execute a native CrewAI kickoff for role handoff synthesis.

        Important:
        - No external side effects are executed here.
        - This only produces coordinated recommendations / execution brief.
        """
        try:
            # Lazy import to keep optional dependency behavior.
            from crewai import Agent, Crew, Process, Task  # type: ignore
        except Exception as exc:
            return {
                "runtime": "native_unavailable",
                "error": f"import_error:{exc}",
            }

        try:
            result = await asyncio.to_thread(
                self._execute_crewai_sync,
                Agent,
                Crew,
                Process,
                Task,
                summary,
                dry_run,
                int(getattr(settings, "AI_EMPLOYEE_CREW_MAX_ITERATIONS", 6)),
            )
            return {
                "runtime": "native",
                "output_preview": self._coerce_crewai_output(result)[:3000],
            }
        except Exception as exc:
            logger.warning("CrewAI native kickoff failed: %s", exc, exc_info=True)
            return {
                "runtime": "native_failed",
                "error": str(exc),
            }

    @staticmethod
    def _execute_crewai_sync(
        Agent: Any,
        Crew: Any,
        Process: Any,
        Task: Any,
        summary: Dict[str, Any],
        dry_run: bool,
        max_iter: int,
    ) -> Any:
        summary_json = json.dumps(summary, ensure_ascii=False)

        cobrador = Agent(
            role="Analista Financeiro",
            goal=(
                "Priorizar cobrança com foco em risco de caixa e inadimplência, "
                "respeitando limites de alçada."
            ),
            backstory=(
                "Especialista em contas a receber. Deve propor ações sem executar "
                "disparos reais nesta etapa."
            ),
            allow_delegation=True,
            max_iter=max(1, max_iter),
            verbose=False,
        )
        contratos = Agent(
            role="Gestor de Contratos",
            goal="Identificar riscos de vencimento contratual e propostas de renovação.",
            backstory="Especialista em ciclo de vida contratual e conformidade operacional.",
            allow_delegation=True,
            max_iter=max(1, max_iter),
            verbose=False,
        )
        analista = Agent(
            role="CFO Assistant",
            goal="Consolidar recomendações executivas com plano de ação e prioridade.",
            backstory="Assistente executivo focado em risco de caixa e governança.",
            allow_delegation=False,
            max_iter=max(1, max_iter),
            verbose=False,
        )

        task_cobrador = Task(
            description=(
                "Com base no resumo operacional, gere priorização de cobrança em 3 níveis "
                "(alto/médio/baixo) e explique por quê. Não executar envio real.\n\n"
                f"dry_run={str(dry_run).lower()}\n"
                f"resumo={summary_json}"
            ),
            expected_output=(
                "Resumo textual curto com prioridades de cobrança e justificativas."
            ),
            agent=cobrador,
        )
        task_contratos = Task(
            description=(
                "Analise risco de contratos (vencidos/a vencer) e proponha ações de renovação "
                "em ordem de prioridade."
            ),
            expected_output=(
                "Resumo textual curto com riscos contratuais e ações sugeridas."
            ),
            agent=contratos,
            context=[task_cobrador],
        )
        task_cfo = Task(
            description=(
                "Consolidar resultado dos agentes em briefing executivo: "
                "Top 5 ações, urgência, dependências e critérios de escalonamento ao CFO."
            ),
            expected_output=(
                "Briefing executivo objetivo com ações priorizadas e próximos passos."
            ),
            agent=analista,
            context=[task_cobrador, task_contratos],
        )

        crew = Crew(
            agents=[cobrador, contratos, analista],
            tasks=[task_cobrador, task_contratos, task_cfo],
            process=Process.sequential,
            verbose=False,
        )
        return crew.kickoff()

    @staticmethod
    def _coerce_crewai_output(value: Any) -> str:
        if value is None:
            return ""
        for attr in ("raw", "output", "result"):
            candidate = getattr(value, attr, None)
            if candidate:
                return str(candidate)
        return str(value)

    async def _execute_role_steps(
        self,
        *,
        dry_run: bool,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], List[AgentAction], List[str]]:
        actions: List[AgentAction] = []
        errors: List[str] = []

        cobrador_data, action, err = await self._run_cobrador_agent(dry_run=dry_run)
        actions.append(action)
        if err:
            errors.append(err)

        contratos_data, action, err = await self._run_contratos_agent(dry_run=dry_run)
        actions.append(action)
        if err:
            errors.append(err)

        analista_data, action, err = await self._run_analista_cfo_agent(dry_run=dry_run)
        actions.append(action)
        if err:
            errors.append(err)

        return cobrador_data, contratos_data, analista_data, actions, errors

    async def _run_cobrador_agent(self, *, dry_run: bool) -> Tuple[Dict[str, Any], AgentAction, Optional[str]]:
        _ = dry_run  # reserved for future non-preview channel execution
        try:
            client_sync = await self.tools.get_client_sync_health()
            financial_sync = await self.tools.get_financial_sync_health()
            email_preview: Dict[str, Any] = {"skipped": True, "reason": "AI_EMPLOYEE_ENABLE_EMAIL_PREVIEW is false"}
            whatsapp_preview: Dict[str, Any] = {"skipped": True, "reason": "AI_EMPLOYEE_ENABLE_WHATSAPP_PREVIEW is false"}

            if bool(getattr(settings, "AI_EMPLOYEE_ENABLE_EMAIL_PREVIEW", True)):
                email_preview = await self.tools.preview_email_billing()

            if bool(getattr(settings, "AI_EMPLOYEE_ENABLE_WHATSAPP_PREVIEW", False)):
                whatsapp_preview = await self.tools.preview_whatsapp_billing()

            data = {
                "client_sync": client_sync,
                "financial_sync": financial_sync,
                "email_preview": email_preview,
                "whatsapp_preview": whatsapp_preview,
            }
            action = AgentAction(
                agent="cobrador",
                action="avaliar_inadimplencia_e_canais",
                details={
                    "eligible_email_clients": int(email_preview.get("eligible_clients") or 0),
                    "eligible_whatsapp_clients": int(whatsapp_preview.get("eligible_clients") or 0),
                    "overdue_records": int(financial_sync.get("overdue_records") or 0),
                },
            )
            await self._persist_action(action)
            return data, action, None
        except Exception as exc:
            action = AgentAction(
                agent="cobrador",
                action="avaliar_inadimplencia_e_canais",
                status="error",
                details={"error": str(exc)},
            )
            await self._persist_action(action)
            return {}, action, f"cobrador:{exc}"

    async def _run_contratos_agent(self, *, dry_run: bool) -> Tuple[Dict[str, Any], AgentAction, Optional[str]]:
        _ = dry_run
        try:
            contracts_snapshot = await self.tools.get_contract_lifecycle_overview(
                days_ahead=int(getattr(settings, "CONTRACT_LIFECYCLE_ALERT_DAYS", 30))
            )
            data = {"lifecycle": contracts_snapshot}
            action = AgentAction(
                agent="contratos",
                action="monitorar_vencimentos",
                details={
                    "monitored_total": int(contracts_snapshot.get("monitored_total") or 0),
                    "expiring_soon_count": int(contracts_snapshot.get("expiring_soon_count") or 0),
                    "overdue_count": int(contracts_snapshot.get("overdue_count") or 0),
                },
            )
            await self._persist_action(action)
            return data, action, None
        except Exception as exc:
            action = AgentAction(
                agent="contratos",
                action="monitorar_vencimentos",
                status="error",
                details={"error": str(exc)},
            )
            await self._persist_action(action)
            return {}, action, f"contratos:{exc}"

    async def _run_analista_cfo_agent(self, *, dry_run: bool) -> Tuple[Dict[str, Any], AgentAction, Optional[str]]:
        _ = dry_run
        try:
            risk_data = await self.tools.get_cash_risk_overview(force_refresh=False)
            snapshot = risk_data.get("snapshot") or {}
            trend = risk_data.get("trend") or {}
            data = {"cash_risk": risk_data}
            action = AgentAction(
                agent="analista_cfo",
                action="calcular_risco_e_projecao",
                details={
                    "risk_level": str(snapshot.get("risk_level") or "").lower(),
                    "projected_15d": float(snapshot.get("projected_15d") or 0.0),
                    "trend": str(trend.get("direction") or "insufficient_data"),
                },
            )
            await self._persist_action(action)
            return data, action, None
        except Exception as exc:
            action = AgentAction(
                agent="analista_cfo",
                action="calcular_risco_e_projecao",
                status="error",
                details={"error": str(exc)},
            )
            await self._persist_action(action)
            return {}, action, f"analista_cfo:{exc}"

    @staticmethod
    def _hydrate_action(payload: Dict[str, Any]) -> AgentAction:
        details = payload.get("details")
        if not isinstance(details, dict):
            details = {"value": details} if details is not None else {}
        return AgentAction(
            agent=str(payload.get("agent") or "unknown"),
            action=str(payload.get("action") or "unknown"),
            status=str(payload.get("status") or "ok"),
            details=details,
            created_at=str(payload.get("created_at") or _utc_now_iso()),
        )

    def _compose_result(
        self,
        *,
        mode: str,
        dry_run: bool,
        started_at: str,
        cobrador_data: Dict[str, Any],
        contratos_data: Dict[str, Any],
        analista_data: Dict[str, Any],
        actions: List[AgentAction],
        errors: List[str],
    ) -> Dict[str, Any]:
        summary = self._build_summary(
            cobrador_data=cobrador_data,
            contratos_data=contratos_data,
            analista_data=analista_data,
        )
        result = OrchestrationResult(
            success=len(errors) == 0,
            mode=mode,
            dry_run=dry_run,
            started_at=started_at,
            finished_at=_utc_now_iso(),
            actions=actions[: max(1, int(getattr(settings, "AI_EMPLOYEE_MAX_ACTIONS_PER_RUN", 50)))],
            summary=summary,
            errors=errors,
        )
        return result.to_dict()

    @staticmethod
    def _build_crewai_plan(summary: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "runtime": "planning_only",
            "agents": [
                {"name": "cobrador", "role": "Analista Financeiro"},
                {"name": "contratos", "role": "Gestor de Contratos"},
                {"name": "analista_cfo", "role": "CFO Assistant"},
            ],
            "tasks": [
                "Priorizar inadimplência e canais de cobrança",
                "Monitorar ciclo de contratos e vencimentos",
                "Avaliar risco de caixa e projeção de 15 dias",
            ],
            "delegation": "deterministic_tools_with_guardrails",
            "handoffs": [
                {
                    "from": "cobrador",
                    "to": "contratos",
                    "context": ["overdue_records", "eligible_email_clients", "eligible_whatsapp_clients"],
                },
                {
                    "from": "contratos",
                    "to": "analista_cfo",
                    "context": ["expiring_soon_count", "overdue_count", "monitored_total"],
                },
            ],
            "governance": {
                "max_grace_days": MAX_AUTONOMOUS_GRACE_DAYS,
                "max_discount_pct": MAX_AUTONOMOUS_DISCOUNT_PCT,
                "max_discount_brl": MAX_AUTONOMOUS_DISCOUNT_VALUE_BRL,
                "max_installments": MAX_AUTONOMOUS_INSTALLMENTS,
                "cfo_mandatory_above_brl": MANDATORY_CFO_APPROVAL_ABOVE_BRL,
            },
            "recommended_actions": list(summary.get("recommended_actions") or [])[:3],
        }

    @staticmethod
    def _requires_cfo_escalation(state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        analista_data = dict(state.get("analista_data") or {})
        cash_risk_payload = dict(analista_data.get("cash_risk") or {})
        cash_snapshot = dict(cash_risk_payload.get("snapshot") or {})
        lifecycle_payload = dict((state.get("contratos_data") or {}).get("lifecycle") or {})

        reasons: List[str] = []
        risk_level = str(cash_snapshot.get("risk_level") or "").strip().lower()
        projected_15d = float(cash_snapshot.get("projected_15d") or 0.0)
        overdue_contracts = int(lifecycle_payload.get("overdue_count") or 0)

        if risk_level == "alto":
            reasons.append("cash_risk_high")
        if projected_15d < 0:
            reasons.append("projected_cash_negative_15d")
        if overdue_contracts > 0:
            reasons.append("contracts_overdue_detected")

        return len(reasons) > 0, reasons

    async def _persist_action(self, action: AgentAction) -> None:
        await self.tools.log_agent_action(
            agent=action.agent,
            action=action.action,
            status=action.status,
            payload=action.to_dict(),
        )

    @staticmethod
    def _build_summary(
        *,
        cobrador_data: Dict[str, Any],
        contratos_data: Dict[str, Any],
        analista_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        email_preview = cobrador_data.get("email_preview") or {}
        whatsapp_preview = cobrador_data.get("whatsapp_preview") or {}
        financial_sync = cobrador_data.get("financial_sync") or {}
        lifecycle = contratos_data.get("lifecycle") or {}
        cash_risk_payload = analista_data.get("cash_risk") or {}
        cash_snapshot = cash_risk_payload.get("snapshot") or {}
        trend = cash_risk_payload.get("trend") or {}

        projected_15d = float(cash_snapshot.get("projected_15d") or 0.0)
        risk_level = str(cash_snapshot.get("risk_level") or "").lower()
        top3_concentration = float(cash_snapshot.get("top3_concentration_pct") or 0.0)
        overdue_records = int(financial_sync.get("overdue_records") or 0)

        recommendations: List[str] = []
        if risk_level == "alto" or projected_15d < 0:
            recommendations.append("Convocar comitê de caixa em 24h.")
        if overdue_records > 0:
            recommendations.append("Priorizar régua de cobrança dos títulos vencidos.")
        if top3_concentration > 60:
            recommendations.append("Reduzir concentração dos 3 maiores clientes.")
        if not recommendations:
            recommendations.append("Manter execução diária e monitoramento de indicadores.")

        return {
            "cobrador": {
                "eligible_email_clients": int(email_preview.get("eligible_clients") or 0),
                "eligible_whatsapp_clients": int(whatsapp_preview.get("eligible_clients") or 0),
                "overdue_records": overdue_records,
            },
            "contratos": {
                "monitored_total": int(lifecycle.get("monitored_total") or 0),
                "expiring_soon_count": int(lifecycle.get("expiring_soon_count") or 0),
                "overdue_count": int(lifecycle.get("overdue_count") or 0),
            },
            "cfo_assistant": {
                "risk_level": risk_level,
                "projected_15d": projected_15d,
                "trend_direction": str(trend.get("direction") or "insufficient_data"),
                "top3_concentration_pct": top3_concentration,
            },
            "guardrails": {
                "max_grace_days": MAX_AUTONOMOUS_GRACE_DAYS,
                "max_discount_pct": MAX_AUTONOMOUS_DISCOUNT_PCT,
                "max_discount_brl": MAX_AUTONOMOUS_DISCOUNT_VALUE_BRL,
                "max_installments": MAX_AUTONOMOUS_INSTALLMENTS,
                "cfo_mandatory_above_brl": MANDATORY_CFO_APPROVAL_ABOVE_BRL,
            },
            "recommended_actions": recommendations[:3],
        }
