import whisper

import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
from pydub import AudioSegment

from pydub import AudioSegment

from google import genai

import re

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
        f.close()
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

def paragraph_modify(text):
    regex = re.compile(r"Paragraph [0-9]:")
    modified_text = regex.sub(lambda match: f"#### {match.group()}\n\n", text)
    # print(regex.search(starting_text).group())
    return modified_text

def key_points(text: str) -> list[str]:
    # Разбиваем по блокам задач

    regex = re.compile(r"Key Points:")
    modified_text = regex.sub(lambda match: f"\n{match.group()}", text)
    # print(regex.search(starting_text).group())
    return modified_text

    
# def task_to_list(text: str) -> list[str]:
#     text = text.replace("\n", "\n\n")
#     pattern = re.compile(r"Task \d+:")
#     # return re.findall(pattern, text)
#     result = pattern.split(text)
#     print(f"{result=}")
#     return result
#     # return text.split("Task")
    
def task_to_list(text: str) -> list[str]:
    # Разбиваем по блокам задач
    tasks = re.split(r"- Task \d+:", text)
    results = []

    for t in tasks:
        t = t.strip()
        if not t:
            continue

        assigned_match = re.search(r"Assigned to:\s*(.*)", t)
        task_match = re.search(r"Task:\s*(.*)", t)
        details_match = re.search(r"Details:\s*(.*)", t, re.DOTALL)

        assigned = assigned_match.group(1).strip() if assigned_match else "Unassigned"
        task = task_match.group(1).strip() if task_match else "No task description"
        details = details_match.group(1).strip() if details_match else "No details"

        results.append(
            f"**Assigned to:** {assigned}\n\n"
            f"**Task:** {task}\n\n"
            f"**Details:** {details}"
        )

    return results
