# 🎧 Transcriptor de Podcasts/Clases con Resumen, Diarización y SRT/VTT

**Objetivo:** Procesar audios largos, transcribir con timestamps y resumir en bullet points.

**Mínimos**
- Subir MP3/WAV (hasta X min).
- Transcripción con timestamps.
- Resumen por bloques.

**Arquitectura**
- UI → STT (batch) → JSON con timestamps → Summarization → UI.

**APIs/Modelos**
- Azure: Speech-to-Text (batch) + Language Summarization.
- Alternativas: AssemblyAI/Deepgram; Whisper + resumen con OpenAI/HF.

**Ampliaciones**
- Diarización (hablantes). (1)
- Export SRT/VTT. (1)


---

## Índice

1. [Como usar la Aplicación](#como-usar-la-aplicación)  
2. [Explicación del Código](#explicación-del-código)  

## Como usar la Aplicación
Sigue estos pasos para utilizar la app correctamente:

### 1️⃣ Abrir la aplicación
Ejecuta el proyecto con:

```bash
streamlit run nombre_del_archivo.py
```
Esto abrirá la aplicación en tu navegador (por defecto en http://localhost:8501).

### 2️⃣ Subir un archivo de audio

- En la parte superior verás la opción “Sube un archivo de audio corto (WAV o MP3)”.
- Selecciona un archivo desde tu ordenador.
- La app mostrará un reproductor para escuchar el audio cargado.

 Consejo: cuanto más corto sea el audio, más rápida será la transcripción.

### 3️⃣ Elegir el número de frases del resumen
Usa el slider (“Número de oraciones en el resumen”) para decidir cuántas frases quieres que tenga el resumen generado por Azure.

### 4️⃣ Procesar el audio
Una vez subido el archivo:
- La app convierte el audio a formato WAV (mono, 16kHz, PCM), que es el que requiere Azure.
- Luego inicia la transcripción con diarización (identificación de hablantes).
- Finalmente, genera un resumen automático usando Azure Language Services.

Todo esto se hace automáticamente, mostrando indicadores de progreso como:
- Convirtiendo audio...
- Transcribiendo y diarizando...
- Generando resumen...

### 5️⃣ Navegar por las pestañas
La aplicación tiene cuatro pestañas principales:
#### Transcripcion
Muestra el texto completo reconocido, con timestamps y nombres de hablantes (ejemplo: `[00:02.50s - 00:05.10s] (Speaker 1)`)
#### Resumen
Presenta el resumen generado automáticamente por Azure Language, con el número de frases que elegiste.
#### Exportación
Permite:
- Elegir el formato (SRT o VTT).
- Pulsar “Exportar” para generar el archivo.
- Luego descargarlo con el botón “Descargar”.

Los archivos exportados sirven como subtítulos para vídeos o editores multimedia.
#### Diarización
Indica cuántos hablantes diferentes se detectaron en el audio.

### 6️⃣ Descargar tus resultados
Una vez exportado el archivo de subtítulos (.srt o .vtt):
- Haz clic en el botón “Descargar”.
- Se descargará el archivo con nombre transcripcion.srt o transcripcion.vtt.

## Explicación del Código

A continuación se explica cada parte del código y su función dentro de la aplicación:

---

### 1. Importación de librerías

```python
import streamlit as st
import requests, time, tempfile, os, re
import azure.cognitiveservices.speech as speechsdk
from pydub import AudioSegment
import threading
```

- Librerías y módulos usados:
  - `streamlit`: framework para crear la interfaz web interactiva.
  - `requests`: para hacer peticiones HTTP (usado para enviar texto a Azure Language Services).
  - `time`: para pausas entre consultas a la API de Azure.
  - `tempfile`: para crear archivos temporales en el sistema.
  - `os`: para acceder a variables de entorno.
  - `re`: expresiones regulares para procesar texto de transcripciones.
  - `azure.cognitiveservices.speech`: SDK de Azure para reconocimiento de voz.
  - `pydub`: para convertir y procesar archivos de audio.
  - `threading`: para manejar eventos y sincronización durante la transcripción.

### 2. Configuración de claves y endpoints de Azure

```python
SPEECH_KEY = os.getenv("SPEECH_KEY") or st.secrets.get("SPEECH_KEY")
SPEECH_REGION = os.getenv("SPEECH_REGION") or st.secrets.get("SPEECH_REGION")
LANGUAGE_KEY = os.getenv("LANGUAGE_KEY") or st.secrets.get("LANGUAGE_KEY")
LANGUAGE_ENDPOINT = os.getenv("LANGUAGE_ENDPOINT") or st.secrets.get("LANGUAGE_ENDPOINT")
```

- Estas líneas buscan las claves y endpoints necesarios para usar los servicios de Azure:
  - `SPEECH_KEY` y `SPEECH_REGION`: para la transcripción de audio.
  - `LANGUAGE_KEY` y `LANGUAGE_ENDPOINT`: para generar resúmenes de texto.
  - Primero intenta obtenerlas desde variables de entorno (`os.getenv`).
  - Si no existen, las busca en los secretos de Streamlit (`st.secrets`).

### 3. Headers para la API de Azure Language

```python
summarization_url = LANGUAGE_ENDPOINT + "language/analyze-text/jobs?api-version=2023-04-01"
headers_lang = {
    "Ocp-Apim-Subscription-Key": LANGUAGE_KEY,
    "Content-Type": "application/json"
}
```

- `summarization_url`: crea la URL del endpoint que permite enviar tareas de análisis de texto (como el resumen).
- `headers_lang`: define los encabezados HTTP necesarios para las peticiones:
  - `Ocp-Apim-Subscription-Key`: tu clave personal de Azure Language.
  - `Content-Type`: indica que enviarás datos en formato JSON.

### 4. Interfaz principal de Streamlit

```python
st.title("🎧 Transcriptor de podcasts/clases (con resumen, diarización y SRT/VTT)")
```
- `st.title`: muestra el título de la app.

```python
uploaded_file = st.file_uploader("Sube un archivo de audio corto (WAV o MP3)", type=["wav", "mp3"])
```
- `st.file_uploader`: permite al usuario subir un archivo de audio en los formatos indicados.
  - El archivo subido se guarda temporalmente en memoria como un objeto `UploadedFile`.

```python
num_de_bloques = st.slider("Número de oraciones en el resumen", 1, 10, 3)
```
- `st.slider`: slider que permite al usuario seleccionar cuántas frases tendrá el resumen generado por Azure (entre 1 y 10).

### 5. Funciones auxiliares

### a) Conversión de segundos a formato de tiempo
```python
def segundos_a_tiempo(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"
```
Convierte un número en segundos (`t`) a formato `hh:mm:ss,ms`, usado por los subtítulos SRT.

**Ejemplo:**  
65.432 → "00:01:05,432"

### b) Generar un archivo .srt
```python
def generar_srt(transcripciones):
    srt = ""
    for i, linea in enumerate(transcripciones, start=1):
        m = re.match(r"\[(\d+\.\d+)s - (\d+\.\d+)s\] \((.*)\) (.*)", linea)
        if m:
            start, end, speaker, text = m.groups()
            srt += f"{i}\n{segundos_a_tiempo(float(start))} --> {segundos_a_tiempo(float(end))}\n{speaker}: {text}\n\n"
    return srt
```
Recorre cada línea de la transcripción.  

Usa una expresión regular `re.match()` para extraer:  

- Tiempo de inicio y fin.  
- Nombre del hablante.  
- Texto transcrito.  

Luego crea una cadena en formato `.srt`, numerando cada bloque.  

Retorna el texto completo del archivo SRT.

### c) Generar un archivo .vtt
```python
def generar_vtt(transcripciones):
    vtt = "WEBVTT\n\n"
    for linea in transcripciones:
        m = re.match(r"\[(\d+\.\d+)s - (\d+\.\d+)s\] \((.*)\) (.*)", linea)
        if m:
            start, end, speaker, text = m.groups()
            vtt += f"{float(start):.3f} --> {float(end):.3f}\n{speaker}: {text}\n\n"
    return vtt
```
Funciona igual que la función de SRT, pero para formato `.vtt` (usado por YouTube o reproductores HTML5).  

El formato es casi el mismo que SRT, pero más simple.

### 6. Transcripción con Azure Speech

```python
@st.cache_data(show_spinner=False)
def transcribir_audio(audio_path):
```
`@st.cache_data`: guarda en caché los resultados para no volver a transcribir el mismo audio cada vez que la app se recarga.

```python
    speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)
    speech_config.speech_recognition_language = "es-ES"
```
- `subscription` y `region`: identifican tu cuenta de Azure.  
- `speech_recognition_language`: define el idioma (español de España).

```python
    audio_input = speechsdk.AudioConfig(filename=audio_path)
```
Carga el archivo de audio local en formato compatible.

```python
    transcriber = speechsdk.transcription.ConversationTranscriber(
        speech_config=speech_config,
        audio_config=audio_input
    )
```
Crea el objeto transcriptor que analiza conversaciones (puede detectar varios hablantes).

### Eventos de Azure Speech

```python
    transcripciones = []
    session_stop_event = threading.Event()
```
Azure trabaja de forma asíncrona, por lo que define funciones que se ejecutan automáticamente al recibir resultados.

- `transcripciones`: lista donde se guardará el texto reconocido.  
- `session_stop_event`: evento que indica cuándo ha terminado la sesión de transcripción.


```python
    def handle_transcribed(evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            start_time = evt.result.offset / 10_000_000
            end_time = start_time + (evt.result.duration / 10_000_000)
            speaker = evt.result.speaker_id or ("Speaker 1" if len(transcripciones) % 2 == 0 else "Speaker 2")
            text = evt.result.text
            transcripciones.append(f"[{start_time:.2f}s - {end_time:.2f}s] ({speaker}) {text}")
```

Esta función se ejecuta cada vez que Azure reconoce un fragmento de voz.

- `evt.result.offset`: marca el momento en que empieza la frase.  
- `evt.result.duration`: cuánto dura la frase.  
- `speaker_id`: identifica quién habló (si está disponible).  

Se guarda todo formateado en la lista `transcripciones`.

```python
    def handle_session_stopped(evt):
        session_stop_event.set()
```
Cuando Azure termina la transcripción, marca el evento como completado para que el programa pueda continuar.

```python
    transcriber.transcribed.connect(handle_transcribed)
    transcriber.session_stopped.connect(handle_session_stopped)
    transcriber.canceled.connect(handle_session_stopped)
```
Vincula los eventos de Azure con las funciones definidas arriba (`transcribed`, `session_stopped`, `canceled`).

```python
    transcriber.start_transcribing_async().get()
    session_stop_event.wait()
    transcriber.stop_transcribing_async().get()
```
- Inicia la transcripción asíncrona.  
- Espera a que termine (`wait()`).  
- Luego detiene la sesión.  
- Finalmente, devuelve la lista de frases reconocidas.

### 7. Generar resumen con Azure Language

```python
@st.cache_data(show_spinner=False)
def generar_resumen(full_text, num_de_bloques):
```
También está cacheado (para no recalcular el resumen si ya se hizo).

```python
    if not full_text.strip():
        return ""
```
Si el texto está vacío, devuelve una cadena vacía.

```python
    body = {
        "displayName": "Summarization from Audio",
        "analysisInput": {"documents": [{"id": "1", "language": "es", "text": full_text}]},
        "tasks": [
            {
                "kind": "ExtractiveSummarization",
                "taskName": "Resumen",
                "parameters": {"sentenceCount": num_de_bloques}
            }
        ]
    }
```
Este `body` define la tarea que se envía a la API de Azure.  
Dice: “haz una tarea de resumen extractivo sobre este texto, con X frases”.

```python
    response = requests.post(summarization_url, headers=headers_lang, json=body)
```
Envía la tarea a Azure Language.  

```python
    if response.status_code != 202:
        return f"Error lanzando job: {response.status_code}"
```
Si no devuelve código `202` (que significa “job aceptado”), algo falló.

```python
    job_url = response.headers["operation-location"]
```
Azure no devuelve el resumen directamente, sino un “job” (tarea asíncrona).  
Aquí obtenemos la URL donde podemos consultar el estado.

```python
    for _ in range(20):
        job_response = requests.get(job_url, headers=headers_lang).json()
        status = job_response["status"]
        if status in ["succeeded", "failed"]:
            break
        time.sleep(2)
```
Pregunta cada 2 segundos si el trabajo ha terminado, máximo 20 veces.

```python
    if job_response["status"] != "succeeded":
        return f"Error en el resumen: {job_response}"
```
Si falló, devuelve el error completo.

```python
    sentences = job_response["tasks"]["items"][0]["results"]["documents"][0]["sentences"]
    resumen = "\n".join(["- " + s["text"] for s in sentences])
    return resumen
```
Extrae las frases que Azure seleccionó como resumen.  
Las une en un texto con formato de lista.

### 8. Lógica principal (cuando se sube un archivo)

```python
if uploaded_file is not None:
```
Solo ejecuta el resto del código si el usuario ha subido un audio.

```python
    st.audio(uploaded_file, format="audio/wav")
```
Muestra un reproductor de audio en la app.

### Guardar y convertir el archivo
```python
    if "audio_path" not in st.session_state:
```
Solo guarda y convierte el archivo una vez (gracias a st.session_state).

```python
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as temp_audio:
            temp_audio.write(uploaded_file.read())
            temp_audio_path = temp_audio.name
```
Crea un archivo temporal donde guarda el audio subido.

```python
        try:
            st.info("Convirtiendo audio a WAV (16kHz, mono, PCM)...")
            audio = AudioSegment.from_file(temp_audio_path)
            audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_wav:
                audio.export(tmp_wav.name, format="wav")
                st.session_state.audio_path = tmp_wav.name
```
Convierte cualquier formato a WAV mono 16kHz PCM, el formato que Azure Speech requiere.  
Guarda la ruta en `session_state.audio_path`.

### Transcripción
```python
    if "transcripciones" not in st.session_state:
        with st.spinner("Transcribiendo y diarizando..."):
            st.session_state.transcripciones = transcribir_audio(st.session_state.audio_path)
```
Si no está cacheada, ejecuta la transcripción.  
Muestra un spinner (“cargando...”) mientras se hace.  
Guarda el resultado en `st.session_state`.

### Preparar texto para el resumen
```python
    transcripciones = st.session_state.transcripciones
    full_text = "\n".join([re.sub(r"\[.*?\] \(.*?\) ", "", t) for t in transcripciones])
```
Crea una cadena con solo el texto hablado, eliminando timestamps y nombres de hablantes.

### Generar resumen (si no está hecho)
```python
    if "resumen" not in st.session_state:
        with st.spinner("Generando resumen..."):
            st.session_state.resumen = generar_resumen(full_text, num_de_bloques)
```
Genera el resumen si aún no está almacenado.

### 9. Tabs

```python
    tab1, tab2, tab3, tab4 = st.tabs(["Transcripción", "Resumen", "Exportación", "Diarización"])
```
Crea 4 pestañas para organizar la información.

### TAB 1 – Transcripción
```python
    with tab1:
        st.subheader("Transcripción completa")
        for linea in transcripciones:
            st.write(linea)
```
Muestra cada línea de la transcripción con su tiempo y hablante.

### TAB 2 – Resumen
```python
    with tab2:
        st.subheader("Resumen automático")
        st.write(resumen)
```
Muestra el resumen generado por Azure.

### TAB 3 – Exportación
```python
    with tab3:
        st.subheader("Exportar subtítulos")
```
Interfaz para exportar la transcripción en formato SRT o VTT.

```python
        formato = st.selectbox("Selecciona formato de subtítulos", ["SRT", "VTT"])
```
Menú desplegable para elegir formato.

```python
        if st.button("Exportar"):
            if formato == "SRT":
                st.session_state.export_content = generar_srt(transcripciones)
            else:
                st.session_state.export_content = generar_vtt(transcripciones)
            st.session_state.export_format = formato
            st.success(f"Archivo {formato} generado! Ahora puedes descargarlo.") 
```
Cuando se pulsa “Exportar”, genera el contenido y lo guarda en `session_state`.  
Así no se vuelve a recalcular si cambias de pestaña.

```python
        if "export_content" in st.session_state and st.session_state.export_content:
            st.download_button(
                label=f"Descargar {st.session_state.export_format}",
                data=st.session_state.export_content,
                file_name=f"transcripcion.{st.session_state.export_format.lower()}",
                mime="text/plain"
            )
```
Si el archivo ya está generado, muestra el botón de descarga.

### TAB 4 – Diarización
```python
    with tab4:
        st.subheader("Diarización aproximada")
        speakers = set()
        for linea in transcripciones:
            m = re.match(r"\[.*?\] \((.*?)\)", linea)
            if m:
                speakers.add(m.group(1))
        st.write(f"Número de hablantes detectados: {len(speakers)}")
```
Analiza las transcripciones para contar cuántos hablantes distintos hay.  
Los nombres (`Speaker 1`, `Speaker 2`, etc.) se extraen con una expresión regular.  
Muestra el número de hablantes detectados.