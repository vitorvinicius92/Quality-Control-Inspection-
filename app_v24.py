
import io
import os
from datetime import datetime, date

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from PIL import Image

# ---------------- Config ----------------
DB_URL = "sqlite:///rnc.db"  # SQLite local
engine = create_engine(DB_URL, poolclass=NullPool, future=True)
QUALITY_PASS = os.getenv("QUALITY_PASS", "qualidade123")  # defina em Secrets

# ---------------- DB ----------------
def init_db():
    with engine.begin() as conn:
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS inspecoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TIMESTAMP NULL,
            rnc_num TEXT,
            emitente TEXT,
            area TEXT,
            pep TEXT,
            titulo TEXT,
            responsavel TEXT,
            descricao TEXT,
            referencias TEXT,
            causador TEXT,              -- CSV dos selecionados
            processo_envolvido TEXT,    -- CSV
            origem TEXT,                -- CSV
            acao_correcao TEXT,         -- CSV
            severidade TEXT,
            categoria TEXT,
            acoes TEXT,
            status TEXT DEFAULT 'Aberta',
            encerrada_em TIMESTAMP NULL,
            encerrada_por TEXT,
            encerramento_obs TEXT,
            eficacia TEXT,
            responsavel_acao TEXT,
            reaberta_em TIMESTAMP NULL,
            reaberta_por TEXT,
            reabertura_motivo TEXT
        );
        """)
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS fotos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspecao_id INTEGER NOT NULL,
            blob BLOB NOT NULL,
            filename TEXT,
            mimetype TEXT,
            tipo TEXT CHECK(tipo IN ('abertura','encerramento','reabertura')) DEFAULT 'abertura'
        );
        """)
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS peps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE
        );
        """)
        # Migrações idempotentes
        for ddl in [
            "ALTER TABLE inspecoes ADD COLUMN referencias TEXT",
            "ALTER TABLE inspecoes ADD COLUMN causador TEXT",
            "ALTER TABLE inspecoes ADD COLUMN processo_envolvido TEXT",
            "ALTER TABLE inspecoes ADD COLUMN origem TEXT",
            "ALTER TABLE inspecoes ADD COLUMN acao_correcao TEXT",
            "ALTER TABLE inspecoes ADD COLUMN rnc_num TEXT",
            "ALTER TABLE inspecoes ADD COLUMN emitente TEXT",
            "ALTER TABLE inspecoes ADD COLUMN pep TEXT"
        ]:
            try:
                conn.exec_driver_sql(ddl)
            except Exception:
                pass

def get_pep_list():
    with engine.begin() as conn:
        df = pd.read_sql(text("SELECT code FROM peps ORDER BY code"), conn)
    return df["code"].tolist() if not df.empty else []

def add_peps_bulk(codes:list):
    codes = [c.strip() for c in codes if c and c.strip()]
    if not codes: return 0
    inserted = 0
    with engine.begin() as conn:
        for code in codes:
            try:
                conn.execute(text("INSERT OR IGNORE INTO peps (code) VALUES (:c)"), {"c": code})
                inserted += 1
            except Exception:
                pass
    return inserted

def insert_inspecao(rec, images: list):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO inspecoes (data, rnc_num, emitente, area, pep, titulo, responsavel, descricao, referencias,
                                   causador, processo_envolvido, origem, acao_correcao,
                                   severidade, categoria, acoes, status, responsavel_acao)
            VALUES (:data, :rnc_num, :emitente, :area, :pep, :titulo, :responsavel, :descricao, :referencias,
                    :causador, :processo_envolvido, :origem, :acao_correcao,
                    :severidade, :categoria, :acoes, :status, :responsavel_acao)
        """), rec)
        inspecao_id = conn.execute(text("SELECT last_insert_rowid()")).scalar_one()
        for img in images:
            conn.execute(text("""
                INSERT INTO fotos (inspecao_id, blob, filename, mimetype, tipo)
                VALUES (:iid, :blob, :name, :mime, 'abertura')
            """), {"iid": inspecao_id, "blob": img["blob"], "name": img["name"], "mime": img["mime"]})
        return inspecao_id

def add_photos(iid:int, images:list, tipo:str):
    with engine.begin() as conn:
        for img in images:
            conn.execute(text("""
                INSERT INTO fotos (inspecao_id, blob, filename, mimetype, tipo)
                VALUES (:iid, :blob, :name, :mime, :tipo)
            """), {"iid": iid, "blob": img["blob"], "name": img["name"], "mime": img["mime"], "tipo": tipo})

def fetch_df():
    with engine.begin() as conn:
        df = pd.read_sql(text("""
            SELECT id, data, rnc_num, emitente, area, pep, titulo, responsavel,
                   severidade, categoria, status, descricao, referencias,
                   causador, processo_envolvido, origem, acao_correcao,
                   acoes, encerrada_em, encerrada_por, encerramento_obs, eficacia,
                   responsavel_acao, reaberta_em, reaberta_por, reabertura_motivo
            FROM inspecoes
            ORDER BY id DESC
        """), conn)
    if "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date
    return df

def fetch_photos(iid:int, tipo:str):
    with engine.begin() as conn:
        df = pd.read_sql(text("""
            SELECT id, blob, filename, mimetype FROM fotos WHERE inspecao_id=:iid AND tipo=:tipo ORDER BY id
        """), conn, params={"iid": iid, "tipo": tipo})
    return df.to_dict("records") if not df.empty else []

def encerrar_inspecao(iid:int, por:str, obs:str, eficacia:str, images:list):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE inspecoes
               SET status='Encerrada',
                   encerrada_em=:dt,
                   encerrada_por=:por,
                   encerramento_obs=:obs,
                   eficacia=:ef
             WHERE id=:iid
        """), {"dt": datetime.now(), "por": por, "obs": obs, "ef": eficacia, "iid": iid})
    if images:
        add_photos(iid, images, "encerramento")

def reabrir_inspecao(iid:int, por:str, motivo:str, images:list):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE inspecoes
               SET status='Em ação',
                   reaberta_em=:dt,
                   reaberta_por=:por,
                   reabertura_motivo=:motivo
             WHERE id=:iid
        """), {"dt": datetime.now(), "por": por, "motivo": motivo, "iid": iid})
    if images:
        add_photos(iid, images, "reabertura")

# ---------------- UI & Auth ----------------
st.set_page_config(page_title="RNC — v2.4 (Cloud)", page_icon="🧭", layout="wide")
st.sidebar.title("RNC — v2.4")
st.sidebar.caption("Campos alinhados ao formulário interno • PEP+descrição • Perfis")

init_db()

# Auth simples: senha para habilitar funções de Qualidade
if "is_quality" not in st.session_state:
    st.session_state.is_quality = False

with st.sidebar.expander("🔐 Entrar (Qualidade) — cadastrar/editar"):
    pwd = st.text_input("Senha (Quality)", type="password", placeholder="Informe a senha")
    if st.button("Entrar como Qualidade"):
        if pwd == QUALITY_PASS:
            st.session_state.is_quality = True
            st.success("Perfil Qualidade ativo.")
        else:
            st.error("Senha incorreta.")
    if st.session_state.is_quality and st.button("Sair"):
        st.session_state.is_quality = False
        st.info("Agora você está como Visitante (somente consulta).")

# Menu por perfil
if st.session_state.is_quality:
    menu = st.sidebar.radio("Navegação", ["Nova RNC", "Consultar/Encerrar/Reabrir", "Exportar", "Gerenciar PEPs"], label_visibility="collapsed")
else:
    menu = st.sidebar.radio("Navegação", ["Consultar/Encerrar/Reabrir", "Exportar"], label_visibility="collapsed")

# Helpers
def files_to_images(uploaded_files):
    out = []
    for up in uploaded_files or []:
        try:
            blob = up.getbuffer().tobytes()
            out.append({"blob": blob, "name": up.name, "mime": up.type or "image/jpeg"})
        except Exception:
            pass
    return out

def show_image_from_blob(blob_bytes, width=360):
    try:
        im = Image.open(io.BytesIO(blob_bytes))
        st.image(im, width=width)
    except Exception:
        st.caption("Não foi possível exibir esta imagem.")

# Listas do formulário interno
CAUSADOR_OPTS = ["Solda","Pintura","Engenharia","Fornecedor","Cliente","Caldeiraria","Usinagem","Planejamento","Qualidade","R.H","Outros"]
PROCESSO_OPTS = ["Comercial","Compras","Planejamento","Recebimento","Produção","Inspeção Final","Segurança","Meio Ambiente","5S","R.H","Outros"]
ORIGEM_OPTS = ["Pintura","Orçamento","Usinagem","Almoxarifado","Solda","Montagem","Cliente","Expedição","Preparação","R.H","Outros"]
ACAO_CORRECAO_OPTS = ["Refugo","Retrabalho","Aceitar sob concessão","Comunicar ao fornecedor","Ver e agir","Limpeza","Manutenção","Solicitação de compra"]

def join_list(lst):
    return "; ".join([x for x in lst if x])

# -------- Nova RNC (Qualidade) --------
if menu == "Nova RNC":
    st.header("Nova RNC (formulário interno)")
    with st.form("form_rnc"):
        col0, col1, col2, col3 = st.columns(4)
        with col0:
            emitente = st.text_input("Emitente", placeholder="Seu nome")
        with col1:
            data_insp = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
        with col2:
            rnc_num = st.text_input("RNC Nº", placeholder="Ex.: 001/2025")
        with col3:
            status = st.text_input("Status inicial", value="Aberta", disabled=True)

        col4, col5, col6 = st.columns(3)
        with col4:
            area = st.text_input("Área/Local", placeholder="Ex.: Correia TR-2011KS-07")
        with col5:
            categoria = st.selectbox("Categoria", ["Segurança","Qualidade","Meio Ambiente","Operação","Manutenção","Outros"])
        with col6:
            severidade = st.selectbox("Severidade", ["Baixa","Média","Alta","Crítica"])

        # PEP com descrição (lista vinda da tabela 'peps')
        pep_list = get_pep_list()
        pep_choice = st.selectbox("PEP (código — descrição)", options=(pep_list + ["Outro"]))
        pep_outro = ""
        if pep_choice == "Outro":
            pep_outro = st.text_input("Informe PEP (código — descrição)")
        pep_final = (pep_outro.strip() if pep_choice == "Outro" else pep_choice)

        # Campos do procedimento
        causador = st.multiselect("Causador", CAUSADOR_OPTS)
        processo = st.multiselect("Processo envolvido", PROCESSO_OPTS)
        origem = st.multiselect("Origem", ORIGEM_OPTS)

        titulo = st.text_input("Título", placeholder="Resumo curto da não conformidade")
        descricao = st.text_area("Descrição da não conformidade", height=180)
        referencias = st.text_area("Referências", placeholder="Normas/procedimentos/desenhos aplicáveis", height=100)
        acao_correcao = st.multiselect("Ação de correção", ACAO_CORRECAO_OPTS)

        responsavel = st.text_input("Responsável pela inspeção", placeholder="Quem identificou")
        responsavel_acao = st.text_input("Responsável pela ação corretiva", placeholder="Quem vai executar")

        fotos = st.file_uploader("Fotos da abertura (JPG/PNG)", type=["jpg","jpeg","png"], accept_multiple_files=True)

        submitted = st.form_submit_button("Salvar RNC")
        if submitted:
            imgs = files_to_images(fotos)
            rec = {
                "data": datetime.combine(data_insp, datetime.min.time()),
                "rnc_num": rnc_num.strip(),
                "emitente": emitente.strip(),
                "area": area.strip(),
                "pep": pep_final or None,
                "titulo": titulo.strip(),
                "responsavel": responsavel.strip(),
                "descricao": descricao.strip(),
                "referencias": referencias.strip(),
                "causador": join_list(causador),
                "processo_envolvido": join_list(processo),
                "origem": join_list(origem),
                "acao_correcao": join_list(acao_correcao),
                "severidade": severidade,
                "categoria": categoria,
                "acoes": "",
                "status": "Aberta",
                "responsavel_acao": responsavel_acao.strip(),
            }
            iid = insert_inspecao(rec, imgs)
            st.success(f"RNC salva! Código: #{iid} (status: Aberta)")

# -------- Consultar / Encerrar / Reabrir --------
elif menu == "Consultar/Encerrar/Reabrir":
    st.header("Consulta de RNCs")
    df = fetch_df()

    colf1, colf2, colf3, colf4, colf5 = st.columns(5)
    with colf1:
        f_status = st.multiselect("Status", ["Aberta","Em análise","Em ação","Bloqueada","Encerrada"])
    with colf2:
        f_sev = st.multiselect("Severidade", ["Baixa","Média","Alta","Crítica"])
    with colf3:
        f_area = st.text_input("Filtrar por Área/Local")
    with colf4:
        f_resp = st.text_input("Filtrar por Responsável")
    with colf5:
        f_pep = st.text_input("Filtrar por PEP")

    if not df.empty:
        if f_status: df = df[df["status"].isin(f_status)]
        if f_sev: df = df[df["severidade"].isin(f_sev)]
        if f_area: df = df[df["area"].str.contains(f_area, case=False, na=False)]
        if f_resp: df = df[df["responsavel"].str.contains(f_resp, case=False, na=False)]
        if f_pep: df = df[df["pep"].fillna("").str.contains(f_pep, case=False, na=False)]

        st.dataframe(df[["id","data","rnc_num","emitente","pep","area","titulo","responsavel",
                         "severidade","categoria","status","encerrada_em","reaberta_em"]],
                     use_container_width=True, hide_index=True)

        st.markdown("---")
        if not df.empty:
            sel_id = st.number_input(
                "Ver RNC (ID)",
                min_value=int(df["id"].min()),
                max_value=int(df["id"].max()),
                value=int(df["id"].iloc[0]),
                step=1
            )
            if sel_id in df["id"].values:
                row = df[df["id"] == sel_id].iloc[0].to_dict()
                st.subheader(f"RNC #{int(row['id'])} — {row['titulo']} [{row['status']}]")
                c1, c2, c3, c4, c5, c6 = st.columns(6)
                c1.metric("Data", str(row["data"]))
                c2.metric("Severidade", row["severidade"])
                c3.metric("Status", row["status"])
                c4.metric("PEP", row.get("pep") or "-")
                c5.metric("RNC Nº", row.get("rnc_num") or "-")
                c6.metric("Emitente", row.get("emitente") or "-")
                st.write(f"**Área/Local:** {row['area']}  \n**Resp. inspeção:** {row['responsavel']}  \n**Resp. ação corretiva:** {row.get('responsavel_acao') or '-'}  \n**Categoria:** {row['categoria']}")
                st.markdown("**Descrição**")
                st.write(row["descricao"] or "-")
                st.markdown("**Referências**")
                st.write(row.get("referencias") or "-")
                st.markdown("**Causador / Processo envolvido / Origem**")
                st.write(f"- **Causador:** {row.get('causador') or '-'}")
                st.write(f"- **Processo:** {row.get('processo_envolvido') or '-'}")
                st.write(f"- **Origem:** {row.get('origem') or '-'}")
                st.markdown("**Ação de correção**")
                st.write(row.get("acao_correcao") or "-")

                tabs = st.tabs(["📸 Abertura", "✅ Encerramento", "♻️ Reabertura"])
                with tabs[0]:
                    for rec in fetch_photos(int(row["id"]), "abertura"):
                        show_image_from_blob(rec["blob"])
                with tabs[1]:
                    enc = fetch_photos(int(row["id"]), "encerramento")
                    if enc:
                        for rec in enc:
                            show_image_from_blob(rec["blob"])
                    else:
                        st.caption("Sem evidências de encerramento.")
                with tabs[2]:
                    rea = fetch_photos(int(row["id"]), "reabertura")
                    if rea:
                        for rec in rea:
                            show_image_from_blob(rec["blob"])
                    else:
                        st.caption("Sem registros de reabertura.")

                if st.session_state.is_quality:
                    st.markdown("---")
                    colA, colB = st.columns(2)
                    with colA:
                        st.subheader("Encerrar RNC")
                        can_close = row["status"] != "Encerrada"
                        with st.form(f"encerrar_{sel_id}"):
                            encerr_por = st.text_input("Encerrada por", placeholder="Nome de quem encerra")
                            encerr_obs = st.text_area("Observações de encerramento", placeholder="O que foi feito? Ação definitiva?")
                            eficacia = st.selectbox("Verificação de eficácia", ["A verificar","Eficaz","Não eficaz"])
                            fotos_enc = st.file_uploader("Evidências (fotos)", type=["jpg","jpeg","png"], accept_multiple_files=True, key=f"enc_{sel_id}")
                            sub = st.form_submit_button("Encerrar RNC", disabled=not can_close)
                            if sub:
                                imgs = files_to_images(fotos_enc)
                                encerrar_inspecao(int(row["id"]), encerr_por.strip(), encerr_obs.strip(), eficacia, imgs)
                                st.success("RNC encerrada. Recarregue para ver o novo status.")

                    with colB:
                        st.subheader("Reabrir RNC")
                        can_reopen = row["status"] == "Encerrada"
                        with st.form(f"reabrir_{sel_id}"):
                            reab_por = st.text_input("Reaberta por", placeholder="Nome de quem reabre")
                            reab_motivo = st.text_area("Motivo da reabertura", placeholder="Ex.: eficácia não comprovada")
                            fotos_reab = st.file_uploader("Fotos (opcional)", type=["jpg","jpeg","png"], accept_multiple_files=True, key=f"reab_{sel_id}")
                            sub2 = st.form_submit_button("Reabrir RNC", disabled=not can_reopen)
                            if sub2:
                                imgs = files_to_images(fotos_reab)
                                reabrir_inspecao(int(row["id"]), reab_por.strip(), reab_motivo.strip(), imgs)
                                st.success("RNC reaberta. Status voltou para 'Em ação'.")
                else:
                    st.info("Você está como Visitante (somente consulta). Para cadastrar/editar, entre como Qualidade.")

# -------- Exportar --------
elif menu == "Exportar":
    st.header("Exportar dados (CSV)")
    df = fetch_df()
    if df.empty:
        st.info("Sem dados para exportar.")
    else:
        csv_bytes = df.to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button("Baixar CSV", data=csv_bytes, file_name="rnc_export_v2_4.csv", mime="text/csv")
        st.caption("As fotos não vão no CSV (ficam no banco).")

# -------- Gerenciar PEPs (Qualidade) --------
elif menu == "Gerenciar PEPs":
    st.header("Gerenciar PEPs (Qualidade)")
    st.caption("Importe ou adicione itens como 'C023553 — ADEQ. ...' para aparecer na lista.")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Adicionar manualmente")
        new_pep = st.text_input("Novo PEP (código — descrição)", placeholder="Ex.: C023553 — ADEQ. ...")
        if st.button("Adicionar PEP"):
            if new_pep.strip():
                n = add_peps_bulk([new_pep.strip()])
                if n:
                    st.success("PEP adicionado.")
                else:
                    st.warning("Este PEP já existe ou é inválido.")
    with col2:
        st.subheader("Importar lista (CSV)")
        up = st.file_uploader("Arquivo CSV com uma coluna chamada 'code'", type=["csv"])
        if up is not None:
            try:
                df_csv = pd.read_csv(up)
            except Exception:
                up.seek(0)
                df_csv = pd.read_csv(up, sep=";")
            if "code" in df_csv.columns:
                n = add_peps_bulk(df_csv["code"].astype(str).tolist())
                st.success(f"{n} PEP(s) importado(s).")
            else:
                st.error("CSV deve conter uma coluna chamada 'code'.")
    st.markdown("---")
    st.subheader("Lista atual de PEPs")
    with engine.begin() as conn:
        df_pep = pd.read_sql(text("SELECT code AS 'PEP — descrição' FROM peps ORDER BY code"), conn)
    st.dataframe(df_pep, use_container_width=True, hide_index=True)
