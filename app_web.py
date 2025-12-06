import os
import datetime  # <--- NUEVO: Para registrar la hora de los chats
import streamlit as st
import base64  # <--- NUEVO: Necesario para crear los links
import gspread
import pypdf
import docx
from google import genai
from google.genai.types import GenerateContentConfig
import pypdf
import docx


# --- FUNCIÓN PARA GUARDAR EN SHEETS ---
def guardar_en_sheets(usuario, respuesta_bot):
    try:
        # Definir el alcance (permisos)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        # Cargar credenciales desde los Secretos de Streamlit
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        
        # Conectar
        client = gspread.authorize(creds)
        
        # Abrir la hoja por su nombre (Asegúrate que se llame IGUAL en Google Sheets)
        sheet = client.open("Historial_CcuBot").sheet1 
        
        # Escribir la fila
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([timestamp, usuario, respuesta_bot])
        
    except Exception as e:
        print(f"Error guardando en Sheets: {e}")

def crear_link_descarga(ruta_archivo, nombre_archivo):
    """Lee un archivo y genera un link HTML con los datos incrustados."""
    try:
        with open(ruta_archivo, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode()
        # Esto crea un link HTML que contiene el archivo dentro
        href = f'<a href="data:application/octet-stream;base64,{b64}" download="{nombre_archivo}">📄 Descargar: {nombre_archivo}</a>'
        return href
    except Exception as e:
        return f"Error al generar link para {nombre_archivo}: {e}"

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Web de CcuBot", page_icon="🤖")

# INTENTO 1: Buscar en secrets.toml (La forma correcta en Streamlit)
if "GEMINI_API_KEY" in st.secrets:
    API_KEY = st.secrets["GEMINI_API_KEY"]
# INTENTO 2: Buscar en variables de entorno (Backup)
else:
    API_KEY = os.environ.get("GEMINI_API_KEY")

# --- 2. FUNCIONES DE CARGA ---

def extraer_texto_pdf(ruta_archivo):
    texto = ""
    try:
        with open(ruta_archivo, 'rb') as archivo:
            lector = pypdf.PdfReader(archivo)
            for pagina in lector.pages:
                texto_pagina = pagina.extract_text()
                if texto_pagina:
                    # LIMPIEZA: Elimina caracteres nulos que rompen a Gemini
                    texto += texto_pagina.replace("\x00", "").replace("\x0c", "") + "\n"
    except Exception as e:
        st.error(f"Error al leer PDF '{ruta_archivo}': {e}")
    return texto

def extraer_texto_docx(ruta_archivo):
    texto = ""
    try:
        documento = docx.Document(ruta_archivo)
        for parrafo in documento.paragraphs:
            texto += parrafo.text + "\n"
    except Exception as e:
        st.error(f"Error al leer DOCX '{ruta_archivo}': {e}")
    return texto

def cargar_base_conocimiento():
    # TRUCO: Obtener la ruta exacta donde vive este archivo .py
    ruta_base = os.path.dirname(os.path.abspath(__file__))
    directorio = os.path.join(ruta_base, "conocimiento_ccusafe")
    
    texto_completo = ""
    lista_archivos = [] 
    
    # Debug: Imprimir en la terminal dónde está buscando (para que tú lo veas)
    print(f"🧐 Buscando archivos en: {directorio}")
    
    if not os.path.isdir(directorio):
        # Si no existe, la crea ahí mismo
        try:
            os.makedirs(directorio)
            print(f"📁 Carpeta creada en: {directorio}")
        except Exception as e:
            st.error(f"No se pudo crear la carpeta: {e}")
        return "", []

    # Escanear archivos (Aceptamos mayúsculas y minúsculas .PDF .pdf)
    archivos = [f for f in os.listdir(directorio) if f.lower().endswith(('.pdf', '.docx'))]
    
    if not archivos:
        print("⚠️ La carpeta existe pero no tiene archivos compatibles (.pdf/.docx)")
    
    for nombre_archivo in archivos:
        lista_archivos.append(nombre_archivo)
        ruta = os.path.join(directorio, nombre_archivo)
        if nombre_archivo.lower().endswith('.pdf'):
            texto_completo += f"\n--- DOC: {nombre_archivo} ---\n"
            texto_completo += extraer_texto_pdf(ruta)
        elif nombre_archivo.lower().endswith('.docx'):
            texto_completo += f"\n--- DOC: {nombre_archivo} ---\n"
            texto_completo += extraer_texto_docx(ruta)
            
    return texto_completo, lista_archivos

def get_gemini_response(history, context, api_key):
    SYSTEM_PROMPT = (
        "Eres CcuBot, asistente de seguridad CcuSafe. "
        "Usa el [CONTEXTO] para responder. "
        "Tus respuestas deben ser BREVES, SIMPLES y fáciles de entender para cualquier persona. "
        "Evita tecnicismos innecesarios. "
        "Si la respuesta es larga, usa listas (bullet points) para resumir. "
        "Si no encuentras la respuesta en el contexto, dilo claramente."
        "Pregunta si el problema es de CCUSAFE o SAFECARD"
        "Cuando tengan problemas de instalacion muestra el archivo Primer Manual"
    )
    
    try:
        client = genai.Client(api_key=api_key)
        
        if not context:
            context = "No hay documentos cargados."
            
        prompt_final = f"""
        {SYSTEM_PROMPT}

        [CONTEXTO / DOCUMENTOS]
        {context}
        
        [HISTORIAL CHAT]
        {history}
        """
        
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt_final
        )
        return response.text
    except Exception as e:
        return f"⚠️ Error técnico: {e}"

# --- 3. INTERFAZ WEB ---

with st.sidebar:
    st.header("Configuración")
    # Verificación de clave
    if not API_KEY:
        API_KEY = st.text_input("Ingresa tu clave API de Gemini:", type="password")
        if not API_KEY:
            st.warning("🔒 Ingresa la clave para activar el bot.")
            st.stop()
    else:
        st.success("✅ Clave API conectada")
    
    if st.button("Recargar Documentos"):
        # --- CORRECCIÓN AQUÍ ---
        # Recibimos DOS variables, no una
        texto, archivos = cargar_base_conocimiento()
        
        # Las guardamos por separado
        st.session_state.conocimiento = texto
        st.session_state.archivos = archivos
        # -----------------------
        st.rerun()

st.title("🤖 Bot de asistencia")

# Carga inicial automática
if "conocimiento" not in st.session_state:
    with st.spinner('Cargando manuales...'):
        # --- CORRECCIÓN AQUÍ TAMBIÉN ---
        texto, archivos = cargar_base_conocimiento()
        
        st.session_state.conocimiento = texto
        st.session_state.archivos = archivos
        # -------------------------------
        
        if not archivos:
            st.warning("⚠️ No encontré archivos en 'conocimiento_ccusafe'.")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Mostrar chat previo
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 4. LÓGICA DE CHAT CON LINKS ---
if prompt := st.chat_input("¿En qué puedo ayudarte hoy?"):
    
    # 1. Mostrar mensaje usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Generar respuesta Gemini
    with st.chat_message("assistant"):
        with st.spinner("Analizando..."):
            # Pasamos lista de archivos al contexto
            nombres_archivos = ", ".join(st.session_state.get("archivos", []))
            contexto_con_nombres = f"Archivos disponibles: [{nombres_archivos}]\n\n" + st.session_state.conocimiento
            
            history_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
            
            #Obtencion de respuesta con Gemini
            response = get_gemini_response(history_str, contexto_con_nombres, API_KEY)
            st.markdown(response)
            
            # --- DETECTOR DE INTENCIÓN DE DESCARGA (VERSIÓN LINKS) ---
            palabras_clave = ["descargar", "bajar", "link", "archivo", "documento","manual"]
            
            # --- DETECTOR DE DESCARGA INTELIGENTE ---
            palabras_clave_descarga = ["descargar", "bajar", "link", "archivo", "documento", "manual", "guia"]
            
            if any(palabra in prompt.lower() for palabra in palabras_clave_descarga):
                st.markdown("---")
                
                todos_los_archivos = st.session_state.get("archivos", [])
                archivos_a_mostrar = []
                prompt_usuario = prompt.lower()

                # 1. FILTRO: Buscar coincidencias
                for archivo in todos_los_archivos:
                    # Limpiamos el nombre (quitamos .pdf y guiones) para comparar mejor
                    nombre_limpio = archivo.lower().replace("_", " ").replace("-", " ").replace(".pdf", "").replace(".docx", "")
                    
                    # Dividimos lo que escribió el usuario en palabras
                    palabras_usuario = prompt_usuario.split()
                    
                    # Si alguna palabra clave del usuario (que tenga más de 3 letras) está en el nombre del archivo...
                    # ...lo agregamos a la lista de "candidatos"
                    for palabra in palabras_usuario:
                        if len(palabra) > 3 and palabra in nombre_limpio:
                            if archivo not in archivos_a_mostrar:
                                archivos_a_mostrar.append(archivo)
                
                # 2. DECISIÓN: ¿Qué mostramos?
                if archivos_a_mostrar:
                    st.markdown(f"### 🎯 Encontré {len(archivos_a_mostrar)} archivo(s) relacionado(s):")
                    lista_final = archivos_a_mostrar
                else:
                    # Si no hubo coincidencias específicas, mostramos todo (comportamiento por defecto)
                    st.markdown("### 📂 Archivos disponibles:")
                    lista_final = todos_los_archivos

                # 3. RENDERIZAR BOTONES
                if not lista_final:
                    st.warning("No hay archivos en la carpeta.")
                else:
                    # Corrección de ruta (Parte 2)
                    ruta_base = os.path.dirname(os.path.abspath(__file__))
                    carpeta = os.path.join(ruta_base, "conocimiento_ccusafe")
                    
                    for archivo in lista_final:
                        ruta_completa = os.path.join(carpeta, archivo)
                        try:
                            with open(ruta_completa, "rb") as f:
                                datos = f.read()
                            
                            mime_type = "application/pdf" if archivo.lower().endswith(".pdf") else "application/octet-stream"
                            
                            st.download_button(
                                label=f"⬇️ Descargar: {archivo}",
                                data=datos,
                                file_name=archivo,
                                mime=mime_type,
                                key=f"btn_{archivo}", # Clave única para evitar errores de duplicados
                                use_container_width=True
                            )
                        except Exception as e:
                            st.error(f"Error cargando {archivo}")
            # -----------------------------------------------------------

    st.session_state.messages.append({"role": "assistant", "content": response})
    
    # GUARDAR EN GOOGLE SHEETS (Automático)
    guardar_en_sheets(prompt, response)

    # Guardar en historial
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("historial_chats.txt", "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] USUARIO: {prompt}\n")
            f.write(f"[{timestamp}] BOT: {response}\n")
            f.write("-" * 50 + "\n")
    except Exception:
        pass