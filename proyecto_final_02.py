import streamlit as st
import requests, time, tempfile, os, re
import azure.cognitiveservices.speech as speechsdk
from pydub import AudioSegment
import threading

# Claves de Azure
SPEECH_KEY = os.getenv("SPEECH_KEY") or st.secrets.get("SPEECH_KEY")
SPEECH_REGION = os.getenv("SPEECH_REGION") or st.secrets.get("SPEECH_REGION")
LANGUAGE_KEY = os.getenv("LANGUAGE_KEY") or st.secrets.get("LANGUAGE_KEY")
LANGUAGE_ENDPOINT = os.getenv("LANGUAGE_ENDPOINT") or st.secrets.get("LANGUAGE_ENDPOINT")

# Headers de Language
summarization_url = LANGUAGE_ENDPOINT + "language/analyze-text/jobs?api-version=2023-04-01"
headers_lang = {
    "Ocp-Apim-Subscription-Key": LANGUAGE_KEY,
    "Content-Type": "application/json"
}

# Interfaz Principal
st.title("🎧 Transcriptor de podcasts/clases (con resumen, diarización y SRT/VTT)")

uploaded_file = st.file_uploader("Sube un archivo de audio (WAV o MP3)", type=["wav", "mp3"])
num_de_bloques = st.slider("Número de oraciones en el resumen", 1, 10, 3)

# Funciones auxiliares
def segundos_a_tiempo(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def generar_srt(transcripciones):
    srt = ""
    for i, linea in enumerate(transcripciones, start=1):
        m = re.match(r"\[(\d+\.\d+)s - (\d+\.\d+)s\] \((.*)\) (.*)", linea)
        if m:
            start, end, speaker, text = m.groups()
            srt += f"{i}\n{segundos_a_tiempo(float(start))} --> {segundos_a_tiempo(float(end))}\n{speaker}: {text}\n\n"
    return srt

def generar_vtt(transcripciones):
    vtt = "WEBVTT\n\n"
    for linea in transcripciones:
        m = re.match(r"\[(\d+\.\d+)s - (\d+\.\d+)s\] \((.*)\) (.*)", linea)
        if m:
            start, end, speaker, text = m.groups()
            vtt += f"{float(start):.3f} --> {float(end):.3f}\n{speaker}: {text}\n\n"
    return vtt

# Transcripción con cache
@st.cache_data(show_spinner=False)
def transcribir_audio(audio_path):
    speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)
    speech_config.speech_recognition_language = "es-ES"
    
    audio_input = speechsdk.AudioConfig(filename=audio_path)
    transcriber = speechsdk.transcription.ConversationTranscriber(
        speech_config=speech_config,
        audio_config=audio_input
    )

    transcripciones = []
    session_stop_event = threading.Event()

    def handle_transcribed(evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            start_time = evt.result.offset / 10_000_000
            end_time = start_time + (evt.result.duration / 10_000_000)
            speaker = evt.result.speaker_id or ("Speaker 1" if len(transcripciones) % 2 == 0 else "Speaker 2")
            text = evt.result.text
            transcripciones.append(f"[{start_time:.2f}s - {end_time:.2f}s] ({speaker}) {text}")

    def handle_session_stopped(evt):
        session_stop_event.set()

    transcriber.transcribed.connect(handle_transcribed)
    transcriber.session_stopped.connect(handle_session_stopped)
    transcriber.canceled.connect(handle_session_stopped)

    transcriber.start_transcribing_async().get()
    session_stop_event.wait()
    transcriber.stop_transcribing_async().get()

    return transcripciones

# Resumen con cache
@st.cache_data(show_spinner=False)
def generar_resumen(full_text, num_de_bloques):
    if not full_text.strip():
        return ""
    
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

    response = requests.post(summarization_url, headers=headers_lang, json=body)
    if response.status_code != 202:
        return f"Error lanzando job: {response.status_code}"

    job_url = response.headers["operation-location"]
    for _ in range(20):
        job_response = requests.get(job_url, headers=headers_lang).json()
        status = job_response["status"]
        if status in ["succeeded", "failed"]:
            break
        time.sleep(2)

    if job_response["status"] != "succeeded":
        return f"Error en el resumen: {job_response}"

    sentences = job_response["tasks"]["items"][0]["results"]["documents"][0]["sentences"]
    resumen = "\n".join(["- " + s["text"] for s in sentences])
    return resumen

# Lógica principal
if uploaded_file is not None:
    st.audio(uploaded_file, format="audio/wav")

    # Guardar temporal
    if "audio_path" not in st.session_state:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as temp_audio:
            temp_audio.write(uploaded_file.read())
            temp_audio_path = temp_audio.name

        # Convertir a WAV compatible con Azure
        try:
            st.info("Convirtiendo audio a WAV (16kHz, mono, PCM)...")
            audio = AudioSegment.from_file(temp_audio_path)
            audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_wav:
                audio.export(tmp_wav.name, format="wav")
                st.session_state.audio_path = tmp_wav.name
        except Exception as e:
            st.error(f"Error al convertir el audio: {e}")
            st.stop()

    # Transcripción (solo si no existe aún)
    if "transcripciones" not in st.session_state:
        with st.spinner("🎧 Transcribiendo y diarizando..."):
            st.session_state.transcripciones = transcribir_audio(st.session_state.audio_path)

    transcripciones = st.session_state.transcripciones
    full_text = "\n".join([re.sub(r"\[.*?\] \(.*?\) ", "", t) for t in transcripciones])

    # Resumen (solo si no existe aún)
    if "resumen" not in st.session_state:
        with st.spinner("Generando resumen..."):
            st.session_state.resumen = generar_resumen(full_text, num_de_bloques)

    resumen = st.session_state.resumen

    # TABS
    tab1, tab2, tab3, tab4 = st.tabs(["Transcripción", "Resumen", "Exportación", "Diarización"])

    # ---- TAB 1: Transcripción ----
    with tab1:
        st.subheader("Transcripción completa")
        for linea in transcripciones:
            st.write(linea)

    # ---- TAB 2: Resumen ----
    with tab2:
        st.subheader("Resumen automático")
        st.write(resumen)

    # ---- TAB 3: Exportación ----
    with tab3:
        st.subheader("Exportar subtítulos")

        # Selector de formato
        formato = st.selectbox("Selecciona formato de subtítulos", ["SRT", "VTT"])

        # Botón de exportar
        if st.button("Exportar"):
            if formato == "SRT":
                st.session_state.export_content = generar_srt(transcripciones)
            else:
                st.session_state.export_content = generar_vtt(transcripciones)
            st.session_state.export_format = formato
            st.success(f"Archivo {formato} generado! Ahora puedes descargarlo.")

        # Botón de descarga solo si ya se ha exportado
        if "export_content" in st.session_state and st.session_state.export_content:
            st.download_button(
                label=f"Descargar {st.session_state.export_format}",
                data=st.session_state.export_content,
                file_name=f"transcripcion.{st.session_state.export_format.lower()}",
                mime="text/plain"
            )

    # ---- TAB 4: Diarización ----
    with tab4:
        st.subheader("👥 Diarización aproximada")
        speakers = set()
        for linea in transcripciones:
            m = re.match(r"\[.*?\] \((.*?)\)", linea)
            if m:
                speakers.add(m.group(1))
        st.write(f"Número de hablantes detectados: {len(speakers)}")
