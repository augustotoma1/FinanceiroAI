# Deploy RAG Knowledge Base - Instruções

## Pré-requisitos
- Acesso SSH ao VPS (76.13.166.36)
- Conectar como root: `ssh root@76.13.166.36`

## Ordem de Execução

Cole cada bloco no terminal SSH **um de cada vez**, aguardando a conclusão antes de colar o próximo.

### Bloco 1 - telegram_bot.py (maior arquivo)
Copie o conteúdo do arquivo `block_1.sh` (sem os comentários)

### Bloco 2 - claude_service.py + knowledge_service.py
Copie o conteúdo do arquivo `block_2.sh`

### Bloco 3 - config.py + main.py + google_drive_service.py
Copie o conteúdo do arquivo `block_3.sh`

### Bloco 4 - knowledge_document.py + sync_knowledge.py + requirements.txt
Copie o conteúdo do arquivo `block_4.sh`

### Bloco 5 - Post-Deploy (backup, deps, DB, restart)
Copie o conteúdo do arquivo `block_5_post_deploy.sh`
Este bloco: faz backup, instala dependências, cria tabela no banco, atualiza .env, reinicia o serviço.

## Verificação Pós-Deploy
Após o Bloco 5, verifique:
```bash
systemctl status agent-financeiro
journalctl -u agent-financeiro -n 30 --no-pager
curl http://localhost:8000/health
```

## Próximos Passos (Google Drive)
1. Criar projeto no Google Cloud Console
2. Ativar Google Drive API
3. Criar Service Account e baixar JSON de credenciais
4. Criar pasta no Google Drive e compartilhar com o email da Service Account
5. Colocar JSON no VPS: `/opt/agent-financeiro-aisatec/secrets/gdrive-creds.json`
6. Editar .env:
```
GOOGLE_DRIVE_ENABLED=true
GOOGLE_DRIVE_FOLDER_ID=<id_da_pasta>
GOOGLE_DRIVE_CREDENTIALS_PATH=/opt/agent-financeiro-aisatec/secrets/gdrive-creds.json
```
7. Reiniciar: `systemctl restart agent-financeiro`
