
# RNC App v2.6 — Streamlit Cloud
- RNC Nº automático (YYYY-NNN)
- PEP (código — descrição) em lista suspensa (gerenciar/ importar em "Gerenciar PEPs")
- Campos do procedimento interno
- Fotos salvas no banco (BLOB)
- PDF por RNC (com logo e fotos) — usa ReportLab
- E-mail automático na abertura e no encerramento

## Como publicar
1. Envie estes arquivos para um repositório no GitHub.
2. No Streamlit Cloud: **Deploy an app** → selecione o repo e confirme `app.py`.
3. Em **Secrets** adicione:
   - QUALITY_PASS="sua_senha"
   - SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO
   - APP_BASE_URL="https://seuapp.streamlit.app" (opcional)
4. Abra o app, suba a **logo** no painel lateral e teste o e-mail (botão de teste).

## Observação
Em ambiente gratuito, o arquivo SQLite pode ser reiniciado em redeploys. Para produção, considere Postgres + S3.
