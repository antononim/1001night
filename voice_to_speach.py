import whisper

import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
from pydub import AudioSegment

from pydub import AudioSegment

from google import genai

# def record_voice(filename="audio.wav", duration=10, samplerate=16000):
#     print(f"🎤 Запись {duration} секунд... Говорите!")
#     audio = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype="float32")
#     sd.wait()  # ждём завершения записи
#     wav.write(filename, samplerate, (audio * 32767).astype(np.int16))  # конвертация в int16
#     print(f"✅ Запись сохранена в {filename}")


def transcribe_voice(filename="audio.wav"):
    model = whisper.load_model("base")
    result = model.transcribe(filename, language="en")
    print("📝 Распознанный текст:")
    print(result["text"])


def convert_mp3_to_wav(mp3_filename, wav_filename="audio.wav"):
    audio = AudioSegment.from_mp3(mp3_filename)
    audio.export(wav_filename, format="wav")
    print(f"✅ Конвертация {mp3_filename} в {wav_filename} завершена.")

# def split_text_by_context(text):
#     max_characters = 200
#     splitter = CharacterTextSplitter(chunk_size=max_characters, chunk_overlap=0)
#     chunks = splitter.split_text(text)
#     return chunks

def transcribe_audio(filebytes):
    with open("temp_audio.wav", "wb") as f:
        f.write(filebytes)
    model = whisper.load_model("base")
    result = model.transcribe("temp_audio.wav", language="en")
    # print("📝 Распознанный текст:")
    return result["text"]

def transcription_keys_model(text):
    standart_prompt = '''
You are an expert text analyst. I will provide a long transcription or text.  

Your task is to: 
1. Break the text into meaningful paragraphs based on context and topic shifts. 
2. For each paragraph, identify and list the key points in a concise manner. 
3. From the entire text, extract all tasks mentioned. For each task, provide:
   - Who the task is assigned to (if mentioned)
   - What the task consists of (the action or objective)
   - Any relevant details or priority/weight of the task

Output the result in structured format like this:

Paragraph 1:
<paragraph text>
Key Points:
- <key point 1>
- <key point 2>

Paragraph 2:
<paragraph text>
Key Points:
- <key point 1>
- <key point 2>

Tasks:
- Task 1:
  Assigned to: <person or team>
  Task: <description of the task>
  Details: <additional details, context, or priority>
- Task 2:
  Assigned to: <person or team>
  Task: <description of the task>
  Details: <additional details, context, or priority>

Do not add any extra commentary. Keep it clear, concise, and structured.

'''
    api_key = "AIzaSyBWwQ3Byxkfs0cw8Qy3i3SI-tJAg1nv_Us"
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=(standart_prompt + "\n\n" + text)
    )
    return response.text
    

def process_meeting_audio(file):
    print(file)
    # convert_mp3_to_wav("audio.mp3", "audio.wav")
    transcription = transcribe_audio(file.getvalue())
    # print(transcription)
    analyse_results = transcription_keys_model(transcription)
    return analyse_results


def text_modify(text):
    parts = text.split("Tasks:", 1)
    if len(parts) == 2:
        before_tasks = parts[0].strip()
        after_tasks = parts[1].strip()
        return before_tasks, after_tasks
    else:
        return text.strip(), ""
    

