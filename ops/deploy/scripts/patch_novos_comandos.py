"""
Patch: New Telegram Bot Commands - Phase 1

New commands to add to telegram_bot_v2.py:
  /fluxo - Cash flow summary (fluxo de caixa)
  /dre - DRE categories overview
  /categorias - Financial categories list
  /centros - Cost centers list
  /vendas - Recent sales
  /resumo - Complete financial overview

Also updates:
  /saldos - Now uses real-time balance API
  /inadimplencia - Enhanced with more detail
  _get_financial_summary() - Uses enhanced v2 summary

These functions should be added BEFORE the setup_commands function
in telegram_bot_v2.py
"""

# ──────────────────────────────────────────────────────────────────────
# NEW COMMAND: /fluxo - Cash Flow Summary
# ──────────────────────────────────────────────────────────────────────

async def cmd_fluxo(update, context):
    """Cash flow summary with projections."""
    await update.message.reply_text("Calculando fluxo de caixa...")

    try:
        access_token, error = await _get_conta_azul_token()
        if error:
            await update.message.reply_text(f"Erro: {error}")
            return

        from app.services.conta_azul_service import ContaAzulService
        service = ContaAzulService()

        fluxo = await service.get_fluxo_caixa_resumo(access_token, periodo_dias=30)

        lines = ["FLUXO DE CAIXA - Projecao 30 dias\n"]

        # Saldos atuais
        total_saldos = fluxo.get("total_saldos", 0)
        lines.append(f"Saldo atual: {_format_brl(total_saldos)}")

        # Receber
        rec_pend = fluxo.get("receber_pendente", 0)
        rec_atr = fluxo.get("receber_atrasado", 0)
        lines.append(f"\nA RECEBER:")
        lines.append(f"  Pendente: {_format_brl(rec_pend)} ({fluxo.get('receber_total_parcelas', 0)} parcelas)")
        if rec_atr > 0:
            lines.append(f"  Atrasado: {_format_brl(rec_atr)}")

        # Pagar
        pag_pend = fluxo.get("pagar_pendente", 0)
        pag_atr = fluxo.get("pagar_atrasado", 0)
        lines.append(f"\nA PAGAR:")
        lines.append(f"  Pendente: {_format_brl(pag_pend)} ({fluxo.get('pagar_total_parcelas', 0)} parcelas)")
        if pag_atr > 0:
            lines.append(f"  Atrasado: {_format_brl(pag_atr)}")

        # Projeção
        proj = fluxo.get("projecao_liquida", 0)
        status_proj = "POSITIVO" if proj >= 0 else "NEGATIVO"
        lines.append(f"\nPROJECAO LIQUIDA: {_format_brl(proj)} ({status_proj})")
        lines.append(f"(Saldo + Receber pendente - Pagar pendente)")

        # Top inadimplentes
        inadimplentes = fluxo.get("inadimplentes", [])
        if inadimplentes:
            lines.append(f"\nTOP INADIMPLENTES ({len(inadimplentes)}):")
            for i, inad in enumerate(inadimplentes[:5], 1):
                lines.append(
                    f"  {i}. {inad['nome'][:25]} - {_format_brl(inad['valor'])} "
                    f"({inad.get('dias_atraso', 0)} dias)"
                )

        # Próximos vencimentos
        prox = fluxo.get("vencimentos_proximos", [])
        if prox:
            lines.append(f"\nPROXIMOS VENCIMENTOS:")
            for v in prox[:8]:
                tipo = "REC" if v["tipo"] == "RECEBER" else "PAG"
                lines.append(f"  [{tipo}] {v['nome'][:22]} - {_format_brl(v['valor'])} ({v['vencimento']})")

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"Error in fluxo: {e}", exc_info=True)
        await update.message.reply_text(f"Erro ao calcular fluxo: {str(e)[:200]}")


# ──────────────────────────────────────────────────────────────────────
# NEW COMMAND: /dre - DRE Categories
# ──────────────────────────────────────────────────────────────────────

async def cmd_dre(update, context):
    """Show DRE category structure."""
    await update.message.reply_text("Buscando estrutura DRE...")

    try:
        access_token, error = await _get_conta_azul_token()
        if error:
            await update.message.reply_text(f"Erro: {error}")
            return

        from app.services.conta_azul_service import ContaAzulService
        service = ContaAzulService()

        dre = await service.get_categorias_dre(access_token)

        if not dre:
            await update.message.reply_text("Estrutura DRE nao disponivel.")
            return

        lines = ["ESTRUTURA DRE\n"]

        if isinstance(dre, list):
            for cat in dre[:20]:
                nome = cat.get("nome", "") or cat.get("name", "")
                tipo = cat.get("tipo", "") or ""
                sub = cat.get("subcategorias", []) or cat.get("children", []) or []
                lines.append(f"[{tipo[:3]}] {nome}")
                for s in sub[:5]:
                    s_nome = s.get("nome", "") or s.get("name", "")
                    lines.append(f"  - {s_nome}")
        elif isinstance(dre, dict):
            for grupo, categorias in dre.items():
                lines.append(f"\n{grupo.upper()}:")
                if isinstance(categorias, list):
                    for cat in categorias[:10]:
                        nome = cat.get("nome", "") if isinstance(cat, dict) else str(cat)
                        lines.append(f"  {nome}")
                        sub = cat.get("subcategorias", []) if isinstance(cat, dict) else []
                        for s in sub[:3]:
                            s_nome = s.get("nome", "") if isinstance(s, dict) else str(s)
                            lines.append(f"    - {s_nome}")

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"Error in DRE: {e}", exc_info=True)
        await update.message.reply_text(f"Erro ao buscar DRE: {str(e)[:200]}")


# ──────────────────────────────────────────────────────────────────────
# NEW COMMAND: /categorias - Financial Categories
# ──────────────────────────────────────────────────────────────────────

async def cmd_categorias(update, context):
    """List financial categories (receitas/despesas)."""
    await update.message.reply_text("Buscando categorias financeiras...")

    try:
        access_token, error = await _get_conta_azul_token()
        if error:
            await update.message.reply_text(f"Erro: {error}")
            return

        from app.services.conta_azul_service import ContaAzulService
        service = ContaAzulService()

        cats = await service.get_categorias(access_token)

        if not cats:
            await update.message.reply_text("Nenhuma categoria encontrada.")
            return

        receitas = [c for c in cats if (c.get("tipo", "") or "").upper() in ("RECEITA", "INCOME", "REVENUE")]
        despesas = [c for c in cats if (c.get("tipo", "") or "").upper() in ("DESPESA", "EXPENSE", "COST")]
        outros = [c for c in cats if c not in receitas and c not in despesas]

        lines = [f"Categorias Financeiras ({len(cats)} total)\n"]

        if receitas:
            lines.append(f"RECEITAS ({len(receitas)}):")
            for c in receitas[:15]:
                nome = c.get("nome", "") or c.get("name", "")
                ativo = c.get("ativo", True)
                status = "" if ativo else " [inativa]"
                lines.append(f"  {nome}{status}")

        if despesas:
            lines.append(f"\nDESPESAS ({len(despesas)}):")
            for c in despesas[:15]:
                nome = c.get("nome", "") or c.get("name", "")
                ativo = c.get("ativo", True)
                status = "" if ativo else " [inativa]"
                lines.append(f"  {nome}{status}")

        if outros:
            lines.append(f"\nOUTROS ({len(outros)}):")
            for c in outros[:10]:
                nome = c.get("nome", "") or c.get("name", "")
                lines.append(f"  {nome}")

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"Error in categorias: {e}", exc_info=True)
        await update.message.reply_text(f"Erro: {str(e)[:200]}")


# ──────────────────────────────────────────────────────────────────────
# NEW COMMAND: /centros - Cost Centers
# ──────────────────────────────────────────────────────────────────────

async def cmd_centros(update, context):
    """List cost centers."""
    await update.message.reply_text("Buscando centros de custo...")

    try:
        access_token, error = await _get_conta_azul_token()
        if error:
            await update.message.reply_text(f"Erro: {error}")
            return

        from app.services.conta_azul_service import ContaAzulService
        service = ContaAzulService()

        centros = await service.get_centros_custo(access_token)

        if not centros:
            await update.message.reply_text("Nenhum centro de custo encontrado.")
            return

        ativos = [c for c in centros if c.get("ativo", True)]
        inativos = [c for c in centros if not c.get("ativo", True)]

        lines = [f"Centros de Custo ({len(centros)} total)\n"]

        lines.append(f"ATIVOS ({len(ativos)}):")
        for c in ativos:
            nome = c.get("nome", "") or c.get("name", "")
            lines.append(f"  {nome}")

        if inativos:
            lines.append(f"\nINATIVOS ({len(inativos)}):")
            for c in inativos[:5]:
                nome = c.get("nome", "") or c.get("name", "")
                lines.append(f"  {nome}")

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"Error in centros: {e}", exc_info=True)
        await update.message.reply_text(f"Erro: {str(e)[:200]}")


# ──────────────────────────────────────────────────────────────────────
# NEW COMMAND: /vendas - Recent Sales
# ──────────────────────────────────────────────────────────────────────

async def cmd_vendas(update, context):
    """List recent sales."""
    await update.message.reply_text("Buscando vendas recentes...")

    try:
        access_token, error = await _get_conta_azul_token()
        if error:
            await update.message.reply_text(f"Erro: {error}")
            return

        from app.services.conta_azul_service import ContaAzulService
        from datetime import datetime, timezone, timedelta
        service = ContaAzulService()

        agora = datetime.now(timezone.utc)
        de = (agora - timedelta(days=90)).strftime("%Y-%m-%d")
        ate = agora.strftime("%Y-%m-%d")

        vendas = await service.get_vendas(access_token, data_de=de, data_ate=ate, limit=20)

        if not vendas:
            await update.message.reply_text("Nenhuma venda encontrada nos ultimos 90 dias.")
            return

        total_vendas = 0.0
        lines = [f"Vendas Recentes (ultimos 90 dias)\n"]

        for i, v in enumerate(vendas[:15], 1):
            numero = v.get("numero", "") or ""
            data = (v.get("data_emissao", "") or "")[:10]
            status = v.get("status", "") or ""
            total = float(v.get("total", 0) or 0)
            total_vendas += total

            cliente_obj = v.get("cliente") or {}
            nome = cliente_obj.get("nome", "") if isinstance(cliente_obj, dict) else ""
            if not nome:
                nome = v.get("descricao", "") or "N/A"

            lines.append(f"{i}. [{status[:8]}] #{numero} - {nome[:25]}")
            lines.append(f"   {_format_brl(total)} ({data})")

        if len(vendas) > 15:
            lines.append(f"\n... e mais {len(vendas) - 15} vendas")

        lines.append(f"\nTotal: {_format_brl(total_vendas)} em {len(vendas)} vendas")

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"Error in vendas: {e}", exc_info=True)
        await update.message.reply_text(f"Erro: {str(e)[:200]}")


# ──────────────────────────────────────────────────────────────────────
# NEW COMMAND: /resumo - Complete Financial Overview
# ──────────────────────────────────────────────────────────────────────

async def cmd_resumo(update, context):
    """Complete financial overview using all Conta Azul data."""
    await update.message.reply_text("Gerando resumo financeiro completo... (pode demorar alguns segundos)")

    try:
        access_token, error = await _get_conta_azul_token()
        if error:
            await update.message.reply_text(f"Erro: {error}")
            return

        from app.services.conta_azul_service import ContaAzulService
        service = ContaAzulService()

        resumo = await service.get_resumo_financeiro_completo(access_token)

        if resumo:
            header = "RESUMO FINANCEIRO COMPLETO\n" + "=" * 35 + "\n\n"
            await update.message.reply_text(header + resumo)
        else:
            await update.message.reply_text("Nao foi possivel gerar o resumo.")

    except Exception as e:
        logger.error(f"Error in resumo: {e}", exc_info=True)
        await update.message.reply_text(f"Erro: {str(e)[:200]}")


# ──────────────────────────────────────────────────────────────────────
# UPDATED: _get_financial_summary using v2 service
# ──────────────────────────────────────────────────────────────────────

async def _get_financial_summary_v2():
    """Enhanced financial summary using Conta Azul API v2 with all new endpoints."""
    try:
        access_token, error = await _get_conta_azul_token()
        if error:
            return f"[Conta Azul indisponivel: {error}]"

        from app.services.conta_azul_service import ContaAzulService
        service = ContaAzulService()

        return await service.get_resumo_financeiro_completo(access_token)

    except Exception as e:
        return f"[Erro ao buscar dados financeiros: {str(e)[:100]}]"


# ──────────────────────────────────────────────────────────────────────
# Registration additions for create_bot_application()
# ──────────────────────────────────────────────────────────────────────
"""
Add these lines in create_bot_application() after existing handlers:

    application.add_handler(CommandHandler("fluxo", cmd_fluxo))
    application.add_handler(CommandHandler("dre", cmd_dre))
    application.add_handler(CommandHandler("categorias", cmd_categorias))
    application.add_handler(CommandHandler("centros", cmd_centros))
    application.add_handler(CommandHandler("vendas", cmd_vendas))
    application.add_handler(CommandHandler("resumo", cmd_resumo))

Add these to setup_commands():

    BotCommand("fluxo", "Fluxo de caixa e projecoes"),
    BotCommand("dre", "Estrutura DRE"),
    BotCommand("categorias", "Categorias financeiras"),
    BotCommand("centros", "Centros de custo"),
    BotCommand("vendas", "Vendas recentes"),
    BotCommand("resumo", "Resumo financeiro completo"),

Replace _get_financial_summary with _get_financial_summary_v2 in handle_message()
"""
