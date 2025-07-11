import streamlit as st
import pandas as pd
from datetime import date, datetime
import time
import json
from google.oauth2.service_account import Credentials
import gspread
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

def upload_to_drive(file, filename, mimetype, folder_id, creds):
    service = build('drive', 'v3', credentials=creds)
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    media = MediaIoBaseUpload(io.BytesIO(file.read()), mimetype=mimetype)
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id,webContentLink,webViewLink'
    ).execute()
    return uploaded.get('id'), uploaded.get('webContentLink'), uploaded.get('webViewLink')


# --- CONFIGURACIÓN GOOGLE SHEETS Y DRIVE ---
service_account_info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
# Cambia el scope para permitir acceso a Google Drive completo
SCOPE = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]
creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPE)
client = gspread.authorize(creds)

# --- HOJAS DE CÁLCULO ---
SHEET_ID = "1288rxOwtZDI3A7kuLnR4AXaI-GKt6YizeZS_4ZvdTnQ"
# --- HOJA DE CHAT ---
sheet_registro = client.open_by_key(SHEET_ID).worksheet("Hoja 1")
sheet_equipos = client.open_by_key(SHEET_ID).worksheet("Equipos")
sheet_empresas = client.open_by_key(SHEET_ID).worksheet("Empresas")
try:
    sheet_chat = client.open_by_key(SHEET_ID).worksheet("Chat")
except:
    sheet_chat = client.open_by_key(SHEET_ID).add_worksheet(title="Chat", rows="1000", cols="4")
    sheet_chat.append_row(["fecha", "usuario", "mensaje", "empresa"])

# --- VIDA ÚTIL POR DEFECTO ---
VIDA_UTIL_DEFECTO = 700

# --- CARGAR DATOS DE EQUIPOS ---
equipos_df = pd.DataFrame(sheet_equipos.get_all_records())
equipos_df.columns = [col.lower().strip() for col in equipos_df.columns]

# --- CARGAR INFORMACIÓN DE EMPRESAS ---
empresas_df = pd.DataFrame(sheet_empresas.get_all_records())
empresas_df.columns = [col.lower().strip() for col in empresas_df.columns]

EQUIPOS_EMPRESA = {}
VIDA_UTIL = {}

for _, row in equipos_df.iterrows():
    empresa = row["empresa"].strip()
    codigo = row["codigo"].strip()
    descripcion = row["descripcion"].strip()
    consumibles = [c.strip() for c in row["consumibles"].split(",")]

    if empresa not in EQUIPOS_EMPRESA:
        EQUIPOS_EMPRESA[empresa] = {}

    EQUIPOS_EMPRESA[empresa][codigo] = {
        "descripcion": descripcion,
        "consumibles": consumibles
    }

    # Leer vida útil desde la hoja
    vidas_utiles = [int(str(v).strip()) if str(v).strip().isdigit() else VIDA_UTIL_DEFECTO for v in str(row.get("vida_util", "")).split(",")]
    for c, vida in zip(consumibles, vidas_utiles):
        VIDA_UTIL[c] = vida


# --- INTERFAZ ---
st.set_page_config(page_title="DeTEK PRO Company", layout="centered")



#---------------LOGO-------------
st.markdown(
    """
    <div style="position: absolute; top: 40px; right: 10px;">
        <img src="https://i0.wp.com/tekpro.com.co/wp-content/uploads/2023/12/cropped-logo-tekpro-main-retina.png?fit=522%2C145&ssl=1" width="260">
    </div>
    """,
    unsafe_allow_html=True
)
st.markdown(
    """
     <h1 style='font-family: Georgia; font-size: 40px; margin-bottom: 0;'>
        <span style='color: #00BDAD;'>DeTEK PRO</span>
        <span style='color: #000; font-size: 24px;'> Company</span>
     </h1>
    """,
    unsafe_allow_html=True
)
st.markdown("---")

# --- CARGAR REGISTROS EXISTENTES ---
data = pd.DataFrame(sheet_registro.get_all_records())
data.columns = [col.lower().strip() for col in data.columns]

st.sidebar.title("Navegación")
pagina = st.sidebar.radio("Ir a:", ["Registro de equipo","Dashboard"])

if pagina == "Dashboard":
    st.markdown("## 📊 Dashboard general")

    # Total de empresas y equipos
    total_empresas = len(EQUIPOS_EMPRESA)
    total_equipos = sum(len(equipos) for equipos in EQUIPOS_EMPRESA.values())

    st.markdown(f"- 🏢 **Empresas registradas:** `{total_empresas}`")
    st.markdown(f"- 🧰 **Equipos registrados:** `{total_equipos}`")

    # Partes más cambiadas
    cambios = data["parte cambiada"].dropna().str.split(";").explode()
    cambios = cambios[cambios.str.strip() != ""]  # eliminar vacíos
    partes_frecuentes = cambios.value_counts().head(5)

    st.markdown("### 🧩 Partes más cambiadas")
    for parte, count in partes_frecuentes.items():
        st.markdown(f"- {parte}: `{count}` cambios")

    # Equipos críticos
    st.markdown("### 🚨 Equipos con partes en estado crítico")
    equipos_criticos = []

    for empresa_k, equipos_k in EQUIPOS_EMPRESA.items():
        for codigo_k, detalles_k in equipos_k.items():
            consumibles_k = detalles_k["consumibles"]
            data_k = data[(data["empresa"] == empresa_k) & (data["codigo"] == codigo_k)]
            estado_partes_k = {parte: 0 for parte in consumibles_k}

            for _, fila in data_k.iterrows():
                horas = fila.get("hora de uso", 0)
                try:
                    horas = float(horas)
                except:
                    horas = 0
                partes_cambiadas = str(fila.get("parte cambiada", "")).split(";")
                for parte in estado_partes_k:
                    if parte in partes_cambiadas:
                        estado_partes_k[parte] = 0
                    else:
                        estado_partes_k[parte] += horas

            for parte, usadas in estado_partes_k.items():
                limite = VIDA_UTIL.get(parte, VIDA_UTIL_DEFECTO)
                if limite - usadas <= 24:
                    equipos_criticos.append(f"{empresa_k} - {codigo_k}")
                    break

    if equipos_criticos:
        for eq in equipos_criticos:
            st.markdown(f"- ⚠️ `{eq}`")
    else:
        st.markdown("- ✅ Sin equipos en estado crítico.")

    # Equipos con más horas acumuladas
    st.markdown("### ⏱️ Top 5 equipos con más horas acumuladas")

    horas_acumuladas = {}

    for _, fila in data.iterrows():
        key = f"{fila['empresa']} - {fila['codigo']}"
        horas = fila.get("hora de uso", 0)
        try:
            horas = float(horas)
        except:
            horas = 0
        horas_acumuladas[key] = horas_acumuladas.get(key, 0) + horas

    top_horas = sorted(horas_acumuladas.items(), key=lambda x: x[1], reverse=True)[:5]
    for equipo, horas in top_horas:
        st.markdown(f"- 🕒 `{equipo}`: `{horas:.1f}` horas")

    # Botón de descarga (simulado como TXT)
    st.markdown("### 📤 Exportar informe")
    st.download_button(
        label="📥 Exportar informe PDF",
        data="Resumen del dashboard generado por DeTEK PRO Company.",
        file_name="informe_dashboard.txt"
    )

    st.stop()


# --- GENERAR LISTA DE EMPRESAS CON ALERTA GLOBAL ---
empresas_visible = []
empresa_mapa = {}

for empresa in sorted(EQUIPOS_EMPRESA.keys()):
    equipos = EQUIPOS_EMPRESA[empresa]
    alerta = "🟢"
    for codigo, detalles in equipos.items():
        consumibles = detalles["consumibles"]
        data_equipo = data[(data["empresa"] == empresa) & (data["codigo"] == codigo)]
        estado_partes = {parte: 0 for parte in consumibles}

        for _, fila in data_equipo.iterrows():
            horas = fila.get("hora de uso", 0)
            try:
                horas = float(horas)
            except:
                horas = 0
            partes_cambiadas = str(fila.get("parte cambiada", "")).split(";")
            for parte in estado_partes:
                if parte in partes_cambiadas:
                    estado_partes[parte] = 0
                else:
                    estado_partes[parte] += horas

        for parte, usadas in estado_partes.items():
            limite = VIDA_UTIL.get(parte, VIDA_UTIL_DEFECTO)
            restantes = limite - usadas
            if restantes <= 24:
                alerta = "⚠️"
                break
            elif restantes <= 192 and alerta != "⚠️":
                alerta = "🔴"

        if alerta in ["⚠️", "🔴"]:
            break

    visible = f"{alerta} {empresa}"
    empresas_visible.append(visible)
    empresa_mapa[visible] = empresa

# --- SELECTBOX DE EMPRESA ---
seleccion_empresa = st.selectbox("Selecciona la empresa:", empresas_visible)
empresa = empresa_mapa[seleccion_empresa]


# --- INFO DE LA EMPRESA EN SIDEBAR ---
info_match = empresas_df[empresas_df["empresa"] == empresa]
info_empresa = info_match.iloc[0].to_dict() if not info_match.empty else {}

# --- INFORMACIÓN DE LA EMPRESA (sidebar) ---
st.sidebar.markdown("### 🏢 Información de la empresa seleccionada")
st.sidebar.markdown(f"**Empresa:** {empresa}")

# Buscar coincidencia robusta
info_match = empresas_df[empresas_df["empresa"].str.strip().str.lower() == empresa.strip().lower()]
info_empresa = info_match.squeeze() if not info_match.empty else {}

# Mostrar información actual

st.sidebar.markdown(f"**Encargado:** {info_empresa.get('encargado', 'No disponible')}")
st.sidebar.markdown(f"**Contacto:** {info_empresa.get('contacto', 'No disponible')}")
st.sidebar.markdown(f"**Ubicación:** {info_empresa.get('ubicacion', 'No disponible')}")
st.sidebar.markdown(f"**Técnico líder Tekpro:** {info_empresa.get('tecnico', 'No disponible')}")

# --- Formulario de edición/restauración de información de la empresa ---
with st.sidebar.expander("✏️ Editar información de la empresa"):
    nuevo_encargado = st.text_input("Encargado", value=info_empresa.get("encargado", ""), key="edit_encargado")
    nuevo_contacto = st.text_input("Contacto", value=info_empresa.get("contacto", ""), key="edit_contacto")
    nueva_ubicacion = st.text_input("Ubicación", value=info_empresa.get("ubicacion", ""), key="edit_ubicacion")
    nuevo_tecnico = st.text_input("Técnico líder Tekpro", value=info_empresa.get("tecnico", ""), key="edit_tecnico")

    if st.button("Guardar cambios", key="guardar_empresa"):
        if not info_match.empty:
            idx = info_match.index[0]
            sheet_empresas.update_cell(idx + 2, empresas_df.columns.get_loc("encargado") + 1, nuevo_encargado)
            sheet_empresas.update_cell(idx + 2, empresas_df.columns.get_loc("contacto") + 1, nuevo_contacto)
            sheet_empresas.update_cell(idx + 2, empresas_df.columns.get_loc("ubicacion") + 1, nueva_ubicacion)
            sheet_empresas.update_cell(idx + 2, empresas_df.columns.get_loc("tecnico") + 1, nuevo_tecnico)
            st.success("✅ Información actualizada correctamente.")
        else:
            nueva_fila = [empresa, nuevo_encargado, nuevo_contacto, nueva_ubicacion, nuevo_tecnico]
            sheet_empresas.append_row(nueva_fila)
            st.success("✅ Empresa registrada correctamente.")

# --- CHAT EN LÍNEA ENTRE APPS ---


# --- INDICADOR DE MENSAJES NUEVOS ---
chat_df_indicator = pd.DataFrame(sheet_chat.get_all_records())
chat_df_indicator.columns = [col.lower().strip() for col in chat_df_indicator.columns]
mensajes_empresa = chat_df_indicator[chat_df_indicator["empresa"] == empresa] if not chat_df_indicator.empty and "empresa" in chat_df_indicator.columns else pd.DataFrame()
ultimo_mensaje = mensajes_empresa["fecha"].max() if not mensajes_empresa.empty and "fecha" in mensajes_empresa.columns else None

# Guardar la fecha del último mensaje leído en session_state
if 'ultimo_mensaje_leido' not in st.session_state or st.session_state.get('empresa_chat_leido') != empresa:
    st.session_state['ultimo_mensaje_leido'] = ultimo_mensaje
    st.session_state['empresa_chat_leido'] = empresa

hay_nuevo = False
if ultimo_mensaje and st.session_state['ultimo_mensaje_leido']:
    hay_nuevo = ultimo_mensaje > st.session_state['ultimo_mensaje_leido']
elif ultimo_mensaje and not st.session_state['ultimo_mensaje_leido']:
    hay_nuevo = True

st.sidebar.markdown("---")
chat_title = "💬 Chat en línea"
if hay_nuevo:
    chat_title += " <span style='color:red;font-size:1.2em;'>●</span>"

with st.sidebar.expander(chat_title, expanded=False):
    chat_df = pd.DataFrame(sheet_chat.get_all_records())
    if not chat_df.empty:
        chat_df.columns = [col.lower().strip() for col in chat_df.columns]
        if "empresa" in chat_df.columns and "usuario" in chat_df.columns and "mensaje" in chat_df.columns and "fecha" in chat_df.columns:
            chat_df = chat_df[chat_df["empresa"] == empresa]
            chat_df = chat_df.tail(30)
            for _, row in chat_df.iterrows():
                st.markdown(f"<span style='color:#00BDAD'><b>{row['usuario']}</b></span> <span style='color:gray;font-size:12px'>({row['fecha']})</span>: {row['mensaje']}", unsafe_allow_html=True)
        else:
            st.info("La hoja de chat no tiene el formato esperado. Asegúrate de que las columnas sean: fecha, usuario, mensaje, empresa.")
    else:
        st.info("No hay mensajes en el chat todavía.")
    st.markdown("---")
    mensaje_chat = st.text_input("Mensaje:", value="", key="chat_mensaje_company")
    if st.button("Enviar mensaje", key="chat_enviar_company"):
        if mensaje_chat.strip():
            sheet_chat.append_row([
                str(datetime.now()),
                empresa,  # El nombre de usuario será el de la empresa
                mensaje_chat.strip(),
                empresa
            ])
            st.success("Mensaje enviado!")
            st.session_state['ultimo_mensaje_leido'] = str(datetime.now())
            st.session_state['empresa_chat_leido'] = empresa
            time.sleep(1)
            st.experimental_rerun()

# --- EQUIPOS DISPONIBLES ---
equipos_empresa = EQUIPOS_EMPRESA.get(empresa, {})
if not equipos_empresa:
    st.warning("⚠️ Esta empresa no tiene equipos asignados.")
    st.stop()

# --- SELECTBOX DE EQUIPO ---
selector_visible = []
estado_equipos = {}

for codigo, detalles in equipos_empresa.items():
    descripcion = detalles["descripcion"]
    consumibles = detalles["consumibles"]
    estado_icono = "🟢"
    data_equipo = data[(data["empresa"] == empresa) & (data["codigo"] == codigo)]
    estado_partes = {parte: 0 for parte in consumibles}

    for _, fila in data_equipo.iterrows():
        horas = fila.get("hora de uso", 0)
        try:
            horas = float(horas)
        except:
            horas = 0
        partes_cambiadas = str(fila.get("parte cambiada", "")).split(";")
        for parte in estado_partes:
            if parte in partes_cambiadas:
                estado_partes[parte] = 0
            else:
                estado_partes[parte] += horas

    for parte, usadas in estado_partes.items():
        limite = VIDA_UTIL.get(parte, VIDA_UTIL_DEFECTO)
        restantes = limite - usadas
        if restantes <= 24:
            estado_icono = "⚠️"
            break
        elif restantes <= 192 and estado_icono != "⚠️":
            estado_icono = "🔴"

    visible = f"{estado_icono} {codigo} - {descripcion}"
    selector_visible.append(visible)
    estado_equipos[visible] = codigo

# --- SELECCIÓN DE PROCESO ---
seleccion = st.selectbox("Selecciona el proceso:", selector_visible)
codigo = estado_equipos[seleccion]
op_row = equipos_df[
    (equipos_df["empresa"].str.strip().str.lower() == empresa.strip().lower()) &
    (equipos_df["codigo"].str.strip().str.lower() == codigo.strip().lower())
]

op_equipo = op_row["op"].values[0] if not op_row.empty else "No disponible"
descripcion = equipos_empresa[codigo]["descripcion"]
consumibles_equipo = equipos_empresa[codigo]["consumibles"]





# --- INFORMACIÓN MULTIMEDIA DEL EQUIPO EN EXPANDER ---
with st.expander("Información adicional del equipo", expanded=False):
    # --- FOTO DEL EQUIPO ---
    st.markdown("####  Foto del equipo")

    def get_drive_direct_url(url):
        """Convierte un enlace de Google Drive tipo /file/d/ID/view a enlace directo de visualización."""
        import re
        match = re.search(r"/file/d/([\w-]+)", url)
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/uc?export=view&id={file_id}"
        return url

    foto_url = op_row["foto_url"].values[0] if "foto_url" in op_row.columns and not op_row.empty else ""
    if foto_url:
        st.markdown(f'''
            <a href="{foto_url}" target="_blank" style="
                display: inline-block;
                padding: 0.5em 1.2em;
                background: #00BDAD;
                color: white;
                border: none;
                border-radius: 1.5em;
                text-decoration: none;
                font-weight: bold;
                font-size: 1.1em;
                margin-bottom: 1em;
                transition: background 0.2s;
            " onmouseover="this.style.background='#009e90'" onmouseout="this.style.background='#00BDAD'">
                IMAGEN EQUIPO
            </a>
        ''', unsafe_allow_html=True)
    else:
        st.info("No hay foto disponible para este equipo. Agrega el enlace en la hoja Equipos.")

    # --- MANUAL PDF ---
    st.markdown("####  Manual del equipo (PDF)")
    manual_url = op_row["manual_url"].values[0] if "manual_url" in op_row.columns and not op_row.empty else ""
    if manual_url:
        st.markdown(f'''
            <a href="{manual_url}" target="_blank" style="
                display: inline-block;
                padding: 0.5em 1.2em;
                background: #0072C6;
                color: white;
                border: none;
                border-radius: 1.5em;
                text-decoration: none;
                font-weight: bold;
                font-size: 1.1em;
                margin-bottom: 1em;
                transition: background 0.2s;
            " onmouseover="this.style.background='#005fa3'" onmouseout="this.style.background='#0072C6'">
                MANUAL PDF
            </a>
        ''', unsafe_allow_html=True)
    else:
        st.info("No hay manual PDF disponible para este equipo. Agrega el enlace en la hoja Equipos.")

# --- FORMULARIO DE REGISTRO INFORMACION DEL EQUIPO--------------
with st.form("registro_form"):
    fecha = st.date_input("Fecha", value=date.today())
    st.markdown(f"**Orden de producción (OP):** `{op_equipo}`")
    partes = st.multiselect("Partes cambiadas hoy", consumibles_equipo)
    observaciones = st.text_area("Observaciones técnicas")

    if st.form_submit_button("Guardar registro"):
        fila = [
            empresa,
            str(fecha),
            op_equipo,
            codigo,
            descripcion,
            0.0,  
            ";".join(partes),
            "",  # Observaciones cliente
            observaciones
        ]
        sheet_registro.append_row(fila)
        st.success("✅ Registro guardado correctamente.")

# --- ESTADO DE CONSUMIBLES ---
st.markdown("### 🔧 Estado de consumibles del proceso seleccionado")
data_equipo = data[(data["empresa"] == empresa) & (data["codigo"] == codigo)]
estado_partes = {parte: 0 for parte in consumibles_equipo}

for _, fila in data_equipo.iterrows():
    horas = fila.get("hora de uso", 0)
    try:
        horas = float(horas)
    except:
        horas = 0
    partes_cambiadas = str(fila.get("parte cambiada", "")).split(";")
    for parte in consumibles_equipo:
        if parte in partes_cambiadas:
            estado_partes[parte] = 0
        else:
            estado_partes[parte] += horas

for parte, usadas in estado_partes.items():
    limite = VIDA_UTIL.get(parte, VIDA_UTIL_DEFECTO)
    restantes = max(limite - usadas, 0)
    porcentaje = min(usadas / limite, 1.0)

    if restantes <= 24:
        color, estado_txt = "⚠️", "Falla esperada"
    elif restantes <= 192:
        color, estado_txt = "🔴", "Crítico"
    elif restantes <= 360:
        color, estado_txt = "🟡", "Advertencia"
    else:
        color, estado_txt = "🟢", "Bueno"

    st.markdown(f"{color} **{parte}** - Estado: `{estado_txt}`")
    st.markdown(f"**Uso:** {usadas:.1f} / {limite} h")
    st.progress(porcentaje)
   