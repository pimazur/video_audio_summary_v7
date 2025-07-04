import streamlit as st
from openai import OpenAI
from dotenv import dotenv_values
from pathlib import Path
from os.path import splitext
from pydub import AudioSegment
import requests


env = dotenv_values(".env")

AUDIO_TRANSCRIBE_MODEL = "whisper-1"

SUMMARY_MODEL = "gpt-4o-mini"

USD_TO_PLN = 0

AUDIO_PATH = Path("audio")

VIDEO_PATH = Path("video")

files_names = {}

model_pricings = {
    "gpt-4o": {
        "input_tokens": 5.00 / 1_000_000,  # per token
        "output_tokens": 15.00 / 1_000_000,  # per token
    },
    "gpt-4o-mini": {
        "input_tokens": 0.150 / 1_000_000,  # per token
        "output_tokens": 0.600 / 1_000_000,  # per token
    },
    "whisper-1": {
        "hours": 0.006 * 60, # per hour
        "minutes": 0.006, # per minute
        "seconds": 0.006 / 60 # per second
    }
}

def get_exchange_rate_usd_pln():
    url = "http://api.nbp.pl/api/exchangerates/rates/A/USD/"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        rate = data['rates'][0]['mid']  # Średni kurs
        return rate
    else:
        print("Błąd w pobieraniu danych:", response.status_code)
        return None

def get_openai_client():
    return OpenAI(api_key=st.session_state["openai_api_key"])

def transcribe_audio_to_text(audio_path):
    openai_client = get_openai_client()
    with open(audio_path, "rb") as f:
        transcript = openai_client.audio.transcriptions.create(
            file=f,
            model=AUDIO_TRANSCRIBE_MODEL,
            response_format="verbose_json"
        )

    return transcript.text

def summarize_text(text):
    openai_client = get_openai_client()
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": f"""
                Napisz streszczenie, stanowiące około 20% następującego tekstu:\n
                {text}
                """
            }
        ]
    )

    usage = {}
    if response.usage:
        usage = {
            "completion_tokens": response.usage.completion_tokens,
            "prompt_tokens": response.usage.prompt_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    return {
        "response": response.choices[0].message.content,
        "usage": usage
    }

def calculate_transcription_cost(audio_path):
    audio = AudioSegment.from_file(audio_path)

    duration_in_minutes = len(audio) / 1000 / 60
    print(duration_in_minutes)
    cost = duration_in_minutes * model_pricings["whisper-1"]["minutes"]
    
    return cost

def save_file(file_path, file_or_str):
    if isinstance(file_or_str, str):
        with open(file_path, "w") as file:
            file.write(file_or_str)
    else:
        with open(file_path, "wb") as file:
            file.write(file_or_str.getvalue())

def get_textfile_content(file_path):
    with open(file_path, "r") as file:
        content = file.read()
    
    return content

def set_files_names(uploaded_file, audio_or_video_path):
    files_names.update(
            {
                "uploaded_file_name": uploaded_file.name,
                "transcription_file_name": splitext(uploaded_file.name)[0] + "_transcription.txt",
                "summary_file_name": splitext(uploaded_file.name)[0] + "_summary.txt"
            }
    )
    files_names.update(
            {
                "uploaded_file_path": audio_or_video_path / files_names["uploaded_file_name"],
                "transcription_file_path": audio_or_video_path / files_names["transcription_file_name"],
                "summary_file_path": audio_or_video_path / files_names["summary_file_name"]
            },
    )

#
# STREAMLIT WIDGETS
#
def my_download_button(data, file_name):
    
    return st.download_button(
        label="Pobierz",
        data=data,
        file_name=file_name,
        mime="text/plain"
    )

def my_text_area(label, value):

    return st.text_area(
        label=label,
        value=value,
        height=200,
        disabled=True
    )

def wait_writing():
    
    return st.markdown(
    'Poczekaj chwilę...  ' \
    '<span style="font-size: 24px;">☕</span>' \
    '<span style="font-size: 24px;">💆‍♂️</span>'
    , unsafe_allow_html=True
)

#
# MAIN
#
st.set_page_config(page_title="video/audio summary")

# OpenAI API key protection
if not st.session_state.get("openai_api_key"):
    if "OPENAI_API_KEY" in env:
        st.session_state["openai_api_key"] = env["OPENAI_API_KEY"]

    else:
        st.header(':movie_camera: :headphones: Video/Audio summary')
        st.info("Dodaj swój klucz API OpenAI aby móc korzystać z tej aplikacji")
        st.session_state["openai_api_key"] = st.text_input("Klucz API", type="password")
        if st.session_state["openai_api_key"]:
            st.rerun()

if not st.session_state.get("openai_api_key"):
    st.stop()

USD_TO_PLN = get_exchange_rate_usd_pln()
AUDIO_PATH.mkdir(exist_ok=True)
VIDEO_PATH.mkdir(exist_ok=True)

st.header(":movie_camera: :headphones: Video/Audio summary")
st.write(
    "Witaj, w tej aplikacji możesz " \
    "zamieniać pliki audio i video na tekst, " \
    "a także generować ich streszczenie."
)

# session_state variables
if "uploaded_file" not in st.session_state:
    st.session_state["uploaded_file"] = False

if "transcription_price" not in st.session_state:
    st.session_state["transcription_price"] = 0

if "summary_price" not in st.session_state:
    st.session_state["summary_price"] = 0


uploaded_file = st.file_uploader("Wybierz plik audio", type=["mp3", "wav", "mp4"])

if uploaded_file:
    
    def process_media_file(uploaded_file, media_type):
        media_path = None
        if media_type == 'audio':
            st.audio(uploaded_file)
            media_path = AUDIO_PATH
        elif media_type == 'video':
            st.video(uploaded_file)
            media_path = VIDEO_PATH

        transcription_col, summary_col = st.columns([0.3, 0.7])
        set_files_names(uploaded_file, media_path)

# TRANSCRIPTION
        if transcription_col.button(f"Transkrybuj {media_type}"):
            if files_names["transcription_file_path"].is_file():
                transcription = my_text_area(
                    f"Transkrybcja {media_type}",
                    get_textfile_content(files_names["transcription_file_path"])
                )

                my_download_button(transcription, files_names["transcription_file_name"])
            else:
                wait_writing_displayed = wait_writing()

                transcription = my_text_area(
                    f"Transkrybcja {media_type}",
                    transcribe_audio_to_text(files_names["uploaded_file_path"])
                )

                st.session_state["transcription_price"] += calculate_transcription_cost(files_names["uploaded_file_path"])

                wait_writing_displayed.empty()

                my_download_button(transcription, files_names["transcription_file_name"])
                save_file(files_names["uploaded_file_path"], uploaded_file)
                save_file(files_names["transcription_file_path"], transcription)

# SUMMARY
        if summary_col.button(f"Streść {media_type}"):
            if files_names["summary_file_path"].is_file():
                summary = my_text_area(
                    f"Streszczenie {media_type}",
                    get_textfile_content(files_names["summary_file_path"])
                )

                my_download_button(summary, files_names["summary_file_name"])

            elif files_names["transcription_file_path"].is_file():
                wait_writing_displayed = wait_writing()

                summary_and_tokens = summarize_text(
                    get_textfile_content(
                        files_names["transcription_file_path"]
                        )
                    )

                input_tokens = summary_and_tokens["usage"]["prompt_tokens"]
                output_tokens = summary_and_tokens["usage"]["completion_tokens"]
                price_for_input_token = model_pricings[SUMMARY_MODEL]["input_tokens"]
                price_for_output_token = model_pricings[SUMMARY_MODEL]["output_tokens"]

                st.session_state["summary_price"] += (
                    input_tokens * price_for_input_token +
                    output_tokens * price_for_output_token
                )

                summary = my_text_area(
                    f"Streszczenie {media_type}",
                    summary_and_tokens["response"]
                    )

                wait_writing_displayed.empty()

                my_download_button(summary, files_names["summary_file_name"])
                save_file(files_names["summary_file_path"], summary)

            else:
                wait_writing_displayed = wait_writing()

                transcription = transcribe_audio_to_text(files_names["uploaded_file_path"])
                summary_and_tokens = summarize_text(transcription)

                st.session_state["transcription_price"] += calculate_transcription_cost(files_names["uploaded_file_path"])

                input_tokens = summary_and_tokens["usage"]["prompt_tokens"]
                output_tokens = summary_and_tokens["usage"]["completion_tokens"]
                price_for_input_token = model_pricings[SUMMARY_MODEL]["input_tokens"]
                price_for_output_token = model_pricings[SUMMARY_MODEL]["output_tokens"]

                st.session_state["summary_price"] += (
                    input_tokens * price_for_input_token +
                    output_tokens * price_for_output_token
                )

                summary = my_text_area(
                    f"Streszczenie {media_type}",
                    summary_and_tokens["response"]
                    )

                wait_writing_displayed.empty()

                my_download_button(summary, files_names["summary_file_name"])
                save_file(files_names["uploaded_file_path"], uploaded_file)
                save_file(files_names["transcription_file_path"], transcription)
                save_file(files_names["summary_file_path"], summary)


    if uploaded_file.type in ["audio/mpeg", "audio/wav", "audio/mp3"]:
        process_media_file(uploaded_file, "audio")

    elif uploaded_file.type in ["video/mp4"]:
        process_media_file(uploaded_file, "video")

#
# PRICING
#
with st.sidebar:
    
    st.write(3 * ":moneybag: ")
    st.write("Tutaj możesz zobaczyć koszt użycia aplikacji:")

    total_cost = st.session_state["transcription_price"] + st.session_state["summary_price"]

    price_usd_col, price_zl_col = st.columns(2)

    with price_usd_col:
        st.metric("Koszt(USD)", f"${total_cost:.4f}")

    with price_zl_col:
        st.metric("Koszt(PLN)", f"{total_cost * USD_TO_PLN:.4f}")

    for _ in range(8):
        st.write("")
    st.markdown(
            """
    <div style="text-align: justify;">
        Tutaj możesz obliczyć koszt samej transkrybcji
        - koszty streszczenia zazwyczaj są dużo niższe.
    </div>
    """,
        unsafe_allow_html=True
        )
    st.write("")   
    st.write("Wpisz długość trwania pliku:")

    hours_col, min_col, sec_col = st.columns(3)
    
    hours = hours_col.number_input(
        label="h",
        min_value=0,
        )
    minutes = min_col.number_input(
        label="min",
        min_value=0,
        max_value=59
        )
    seconds = sec_col.number_input(
        label="sec",
        min_value=0,
        max_value=59
        )
    
    transcription_cost = (
        hours * model_pricings["whisper-1"]["hours"] +
        minutes * model_pricings["whisper-1"]["minutes"] +
        seconds * model_pricings["whisper-1"]["seconds"]
    )

    price_usd_col, price_zl_col = st.columns(2)

    with price_usd_col:
        st.metric(
            label="Koszt(USD)",
            value=f"{transcription_cost:.4f}",
            label_visibility="visible"
        )

    with price_zl_col:
        st.metric(
            label="Koszt(PLN)",
            value=f"{transcription_cost * USD_TO_PLN:.4f}",
            label_visibility="visible"
        )