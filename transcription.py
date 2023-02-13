import os 
import argparse
import librosa
import re
import json
import subprocess
import whisper
import moviepy.editor as mp
from whisper.transcribe import detect_language_custom
from ast import literal_eval

def language_detection_test(detection_result_path, model, audio_path):
    """
    Detect language type for audio containing speech of mutliple languages. 
    """
    detection_length_unit_seconds = 2
    audio_total_length_seconds = librosa.get_duration(filename=audio_path)
    i = 0
    result = []
    while i < audio_total_length_seconds:
        detected_language = detect_language_custom(
                model,
                str(audio_path),
                start_second = i,
                detection_duration_seconds = detection_length_unit_seconds,
            )
        if (len(result) > 0 and result[-1]['lang'] == detected_language):
            i += detection_length_unit_seconds
            continue
        else:
            result.append({'start': i, 'lang': detected_language})
            i += detection_length_unit_seconds
        
    with open(detection_result_path, "w", encoding='UTF-8') as text_file:
        for i in range(len(result)):
            duration = 0
            if (i < len(result)-1):
                duration = result[i+1]['start'] - result[i]['start']
            else:
                duration = audio_total_length_seconds - result[i]['start']
            result[i]['duration'] = duration
            text_file.write(json.dumps(result[i]) + '\n')
        text_file.close()
    
    return result

def transcribe_using_detection(detection_result_path, model, audio_path):
    """
    Transcribe the audio using 
    detection_result_path: File containing dicts of the following format: {start:float, duration_seconds:float, language:string}
    """
    if not os.path.exists(detection_result_path):
        language_detection_test(detection_result_path, model, audio_path)
    res = open(detection_result_path).readlines()
    args = dict()
    transcription_results = []
    for line in res:
        #start, duration, lang = line.split(", ")
        lang_section = json.loads(line)
        start = int(float(lang_section['start']))
        duration = int(float(lang_section['duration']))
        args['language'] = re.sub(r'\s','',lang_section['lang'])
        print ("Transcribing at ", start, " for language: ", args['language'])
        transcriptions = whisper.transcribe(
            model,
            str(audio_path),
            logprob_threshold=-1.0,
            start_second = start,
            duration_seconds = duration,
            **args,
        )['segments']
        for transcription in transcriptions:
            transcription_results.append({'start': start + float(transcription['start']), 'text': transcription['text'], 'lang': args['language']})
        
    result_txt_name = os.path.join('out', os.path.basename(audio_path).split('.')[0] + "_" + 'individual_lang' + ".txt")
    with open(result_txt_name, "w", encoding='UTF-8') as text_file:
        for i in range(len(transcription_results)):
            text_file.write(str(transcription_results[i] ) + '\n')
    text_file.close()

# For testing purposes only
def transcribe_to_language(model, audio_path):
    languages = ['', 'English', 'Korean', 'Japanese', 'Chinese']
    for i in range(len(languages)):
        language = languages[i]
        args = dict()
        if (language != ''):
            args['language'] = language
            print("Transcribing for language " + language + "...")
        else:
            print("Transcribing for auto detected language...")
        
        result = whisper.transcribe(
            model,
            str(audio_path),
            **args,
        )
        
        result_txt_name = os.path.split(os.path.basename(audio_path))[0] + "_" + language + ".txt"
        with open(result_txt_name, "w", encoding='UTF-8') as text_file:
            for j in range(len(result['segments'])):
                segment = result['segments'][j]
                text_file.write(str(segment) + '\n')
        text_file.close()
    
#directory paths 
parser = argparse.ArgumentParser(description='Script for organizing footage to folders.')
parser.add_argument("testfile_path", help="path for the test file.")
args = parser.parse_args()

audio_path = args.testfile_path

if (os.path.splitext(audio_path)[1] == '.mp4'):
    testvideo_path = os.path.abspath(audio_path)
    video_audio_wav = os.path.splitext(testvideo_path)[0]+".mp3"
    mp.VideoFileClip(testvideo_path).audio.write_audiofile(video_audio_wav)
    audio_path = video_audio_wav


# result  = subprocess.run(["ffmpeg", "-i", str(testvideo_path), "-vn", "-acodec", "copy", str(video_audio_wav)])
# result = model.transcribe(testfile_path)

modeltype = 'medium'
print("Loading langauge model " + modeltype + "...")

model = whisper.load_model(modeltype)
# language_detection_test('out/detection_result.txt', model, audio_path)
transcribe_using_detection("out/detection_result.txt", model, audio_path)

#model = whisper.load_model("medium")
#transcribe_to_language(model, audio_path)