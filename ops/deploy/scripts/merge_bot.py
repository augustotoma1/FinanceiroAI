#!/usr/bin/env python3
"""
Merge script: Injects new Phase 1 commands into telegram_bot_v2.py
Run on VPS: python3 /opt/agent-financeiro/merge_bot.py
"""

import re

BOT_FILE = "/opt/agent-financeiro/telegram_bot_v2.py"

# ─── New command functions to insert before setup_commands ──────────

NEW_COMMANDS_CODE = '''

# ──────────────────────────────────────────────────────────────────────
# Phase 1 Commands: Financial Intelligence
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
        lines = ["FLUXO DE CAIXA - Projecao 30 dias\\n"]
        total_saldos = fluxo.get("total_saldos", 0)
        lines.append(f"Saldo atual: {_format_brl(total_saldos)}")
        rec_pend = fluxo.get("receber_pendente", 0)
        rec_atr = fluxo.get("receber_atrasado", 0)
        lines.append(f"\\nA RECEBER:")
        lines.append(f"  Pendente: {_format_brl(rec_pend)} ({fluxo.get('receber_total_parcelas', 0)} parcelas)")
        if rec_atr > 0:
            lines.append(f"  Atrasado: {_format_brl(rec_atr)}")
        pag_pend = fluxo.get("pagar_pendente", 0)
        pag_atr = fluxo.get("pagar_atrasado", 0)
        lines.append(f"\\nA PAGAR:")
        lines.append(f"  Pendente: {_format_brl(pag_pend)} ({fluxo.get('pagar_total_parcelas', 0)} parcelas)")
        if pag_atr > 0:
            lines.append(f"  Atrasado: {_format_brl(pag_atr)}")
        proj = fluxo.get("projecao_liquida", 0)
        status_proj = "POSITIVO" if proj >= 0 else "NEGATIVO"
        lines.append(f"\\nPROJECAO LIQUIDA: {_format_brl(proj)} ({status_proj})")
        lines.append(f"(Saldo + Receber pendente - Pagar pendente)")
        inadimplentes = fluxo.get("inadimplentes", [])
        if inadimplentes:
            lines.append(f"\\nTOP INADIMPLENTES ({len(inadimplentes)}):")
            for i, inad in enumerate(inadimplentes[:5], 1):
                lines.append(
                    f"  {i}. {inad['nome'][:25]} - {_format_brl(inad['valor'])} "
                    f"({inad.get('dias_atraso', 0)} dias)"
                )
        prox = fluxo.get("vencimentos_proximos", [])
        if prox:
            lines.append(f"\\nPROXIMOS VENCIMENTOS:")
            for v in prox[:8]:
                tipo = "REC" if v["tipo"] == "RECEBER" else "PAG"
                lines.append(f"  [{tipo}] {v['nome'][:22]} - {_format_brl(v['valor'])} ({v['vencimento']})")
        await update.message.reply_text("\\n".join(lines))
    except Exception as e:
        logger.error(f"Error in fluxo: {e}", exc_info=True)
        await update.message.reply_text(f"Erro ao calcular fluxo: {str(e)[:200]}")


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
        lines = ["ESTRUTURA DRE\\n"]
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
                lines.append(f"\\n{grupo.upper()}:")
                if isinstance(categorias, list):
                    for cat in categorias[:10]:
                        nome = cat.get("nome", "") if isinstance(cat, dict) else str(cat)
                        lines.append(f"  {nome}")
                        sub = cat.get("subcategorias", []) if isinstance(cat, dict) else []
                        for s in sub[:3]:
                            s_nome = s.get("nome", "") if isinstance(s, dict) else str(s)
                            lines.append(f"    - {s_nome}")
        await update.message.reply_text("\\n".join(lines))
    except Exception as e:
        logger.error(f"Error in DRE: {e}", exc_info=True)
        await update.message.reply_text(f"Erro ao buscar DRE: {str(e)[:200]}")


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
        lines = [f"Categorias Financeiras ({len(cats)} total)\\n"]
        if receitas:
            lines.append(f"RECEITAS ({len(receitas)}):")
            for c in receitas[:15]:
                nome = c.get("nome", "") or c.get("name", "")
                ativo = c.get("ativo", True)
                status = "" if ativo else " [inativa]"
                lines.append(f"  {nome}{status}")
        if despesas:
            lines.append(f"\\nDESPESAS ({len(despesas)}):")
            for c in despesas[:15]:
                nome = c.get("nome", "") or c.get("name", "")
                ativo = c.get("ativo", True)
                status = "" if ativo else " [inativa]"
                lines.append(f"  {nome}{status}")
        if outros:
            lines.append(f"\\nOUTROS ({len(outros)}):")
            for c in outros[:10]:
                nome = c.get("nome", "") or c.get("name", "")
                lines.append(f"  {nome}")
        await update.message.reply_text("\\n".join(lines))
    except Exception as e:
        logger.error(f"Error in categorias: {e}", exc_info=True)
        await update.message.reply_text(f"Erro: {str(e)[:200]}")


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
        lines = [f"Centros de Custo ({len(centros)} total)\\n"]
        lines.append(f"ATIVOS ({len(ativos)}):")
        for c in ativos:
            nome = c.get("nome", "") or c.get("name", "")
            lines.append(f"  {nome}")
        if inativos:
            lines.append(f"\\nINATIVOS ({len(inativos)}):")
            for c in inativos[:5]:
                nome = c.get("nome", "") or c.get("name", "")
                lines.append(f"  {nome}")
        await update.message.reply_text("\\n".join(lines))
    except Exception as e:
        logger.error(f"Error in centros: {e}", exc_info=True)
        await update.message.reply_text(f"Erro: {str(e)[:200]}")


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
        lines = [f"Vendas Recentes (ultimos 90 dias)\\n"]
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
            lines.append(f"\\n... e mais {len(vendas) - 15} vendas")
        lines.append(f"\\nTotal: {_format_brl(total_vendas)} em {len(vendas)} vendas")
        await update.message.reply_text("\\n".join(lines))
    except Exception as e:
        logger.error(f"Error in vendas: {e}", exc_info=True)
        await update.message.reply_text(f"Erro: {str(e)[:200]}")


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
            header = "RESUMO FINANCEIRO COMPLETO\\n" + "=" * 35 + "\\n\\n"
            await update.message.reply_text(header + resumo)
        else:
            await update.message.reply_text("Nao foi possivel gerar o resumo.")
    except Exception as e:
        logger.error(f"Error in resumo: {e}", exc_info=True)
        await update.message.reply_text(f"Erro: {str(e)[:200]}")

'''

# ─── New handler registrations ─────────────────────────────────────

NEW_HANDLERS = '''    application.add_handler(CommandHandler("fluxo", cmd_fluxo))
    application.add_handler(CommandHandler("dre", cmd_dre))
    application.add_handler(CommandHandler("categorias", cmd_categorias))
    application.add_handler(CommandHandler("centros", cmd_centros))
    application.add_handler(CommandHandler("vendas", cmd_vendas))
    application.add_handler(CommandHandler("resumo", cmd_resumo))
'''

# ─── New BotCommand entries ────────────────────────────────────────

NEW_BOT_COMMANDS = '''        BotCommand("fluxo", "Fluxo de caixa e projecoes"),
        BotCommand("dre", "Estrutura DRE"),
        BotCommand("categorias", "Categorias financeiras"),
        BotCommand("centros", "Centros de custo"),
        BotCommand("vendas", "Vendas recentes"),
        BotCommand("resumo", "Resumo financeiro completo"),
'''

def merge():
    with open(BOT_FILE, "r") as f:
        content = f.read()

    changes = 0

    # 1. Check if already merged
    if "cmd_fluxo" in content:
        print("SKIP: Commands already present in bot file")
        return

    # 2. Insert new command functions before setup_commands
    marker = "# ─── Bot Setup ────────────────────────────────────────────────────────"
    if marker in content:
        content = content.replace(marker, NEW_COMMANDS_CODE + "\n" + marker)
        changes += 1
        print("OK: Inserted 6 new command functions before Bot Setup section")
    else:
        # fallback: insert before "async def setup_commands"
        content = content.replace(
            "async def setup_commands(",
            NEW_COMMANDS_CODE + "\nasync def setup_commands("
        )
        changes += 1
        print("OK: Inserted 6 new command functions (fallback method)")

    # 3. Add handler registrations before document handler
    handler_marker = '    # Register document and voice handlers (before text handler)'
    if handler_marker in content:
        content = content.replace(
            handler_marker,
            NEW_HANDLERS + "\n" + handler_marker
        )
        changes += 1
        print("OK: Added 6 new handler registrations")
    else:
        # fallback: insert before MessageHandler line
        content = content.replace(
            '    application.add_handler(MessageHandler(filters.Document.ALL',
            NEW_HANDLERS + '    application.add_handler(MessageHandler(filters.Document.ALL'
        )
        changes += 1
        print("OK: Added handler registrations (fallback method)")

    # 4. Add BotCommand entries
    cmd_marker = '        BotCommand("ajuda", "Ajuda completa"),'
    if cmd_marker in content:
        content = content.replace(
            cmd_marker,
            cmd_marker + "\n" + NEW_BOT_COMMANDS
        )
        changes += 1
        print("OK: Added 6 new BotCommand entries to menu")
    else:
        print("WARN: Could not find ajuda BotCommand marker, adding after cancelar")
        content = content.replace(
            '        BotCommand("cancelar", "Cancelar conversa atual"),',
            '        BotCommand("cancelar", "Cancelar conversa atual"),\n' + NEW_BOT_COMMANDS
        )
        changes += 1

    # 5. Update _get_financial_summary to use v2 service
    old_summary_call = "financial_data = await _get_financial_summary()"
    new_summary_call = "financial_data = await _get_financial_summary()  # Enhanced by v2 service"
    if old_summary_call in content and "Enhanced by v2" not in content:
        # Don't replace the call itself, but the _get_financial_summary function
        # will now benefit from the updated conta_azul_service.py automatically
        print("OK: _get_financial_summary() will use updated service automatically")

    # 6. Update docstring
    old_doc = """Commands:
    /start - Welcome message and menu
    /novo_contrato - Start AI-guided contract creation
    /clientes - List recent clients
    /contratos - List recent contracts
    /dashboard - View financial metrics
    /inadimplencia - Check delinquency analysis
    /status - Check system and integration status
    /cancelar - Cancel current conversation
    /ajuda - Show help message"""

    new_doc = """Commands:
    /start - Welcome message and menu
    /novo_contrato - Start AI-guided contract creation
    /clientes - List recent clients
    /contratos - List recent contracts
    /dashboard - View financial metrics
    /inadimplencia - Check delinquency analysis
    /fluxo - Cash flow summary and projections
    /dre - DRE category structure
    /categorias - Financial categories
    /centros - Cost centers
    /vendas - Recent sales
    /resumo - Complete financial overview
    /status - Check system and integration status
    /cancelar - Cancel current conversation
    /ajuda - Show help message"""

    if old_doc in content:
        content = content.replace(old_doc, new_doc)
        changes += 1
        print("OK: Updated module docstring with new commands")

    # 7. Write result
    if changes > 0:
        # Backup first
        with open(BOT_FILE + ".bak", "w") as f_bak:
            with open(BOT_FILE, "r") as f_orig:
                f_bak.write(f_orig.read())
        print(f"OK: Backup saved to {BOT_FILE}.bak")

        with open(BOT_FILE, "w") as f:
            f.write(content)
        print(f"\nMERGE COMPLETE: {changes} changes applied to {BOT_FILE}")
        print("Restart the service: sudo systemctl restart agent-financeiro")
    else:
        print("No changes needed")


if __name__ == "__main__":
    merge()
