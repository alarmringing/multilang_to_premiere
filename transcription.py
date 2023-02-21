import os 
import argparse
import librosa
import sys
import re
import json
import torch
import ffmpeg 
import numpy as np
from datetime import timedelta
import whisper
from typing import Any, Deque, Iterator, List, Dict
import moviepy.editor as mp
from whisper.transcribe import detect_language_custom
from ast import literal_eval

VAD_SEGMENT_PAD = 0.05

def language_detection_test(detection_result_path, model, audio_path, pre_transcribe_segments=None):
    """
    Detect language type for audio containing speech of mutliple languages. 
    """
    print("Detecting language for " + audio_path)
    
    minimum_probability = 0.5
    detection_segment_unit_seconds = 2
    min_detection_segment_unit = 1.5
    audio_total_length_seconds = librosa.get_duration(filename=audio_path)
        
    if pre_transcribe_segments == None:    
        pre_transcribe_segments = [{'start':0, 'end':audio_total_length_seconds}]

    result = []
    for segment in pre_transcribe_segments:       
        start = max(segment['start'] - VAD_SEGMENT_PAD, 0.0)
        end = min(segment['end'] + VAD_SEGMENT_PAD, audio_total_length_seconds)                   
        
        while start < end:
            duration = detection_segment_unit_seconds
            if (end - (start + duration) < min_detection_segment_unit) or (start + detection_segment_unit_seconds > end):
                duration = end - start
            detected_language, probs = detect_language_custom(
                    model,
                    str(audio_path),
                    start_second = start,
                    detection_duration_seconds = duration,
                )
            if (probs < minimum_probability):
                detected_language = 'nil'
            if (len(result) > 0 and result[-1]['lang'] == detected_language):
                start += detection_segment_unit_seconds
                continue
            else:
                result.append({'start': start, 'lang': detected_language})
                start += detection_segment_unit_seconds
        
    print("Saving detection to " + detection_result_path)
    with open(detection_result_path, "w+", encoding='UTF-8') as text_file:
        for i in range(len(result)):
            duration = 0
            if (i < len(result)-1):
                duration = result[i+1]['start'] - result[i]['start']
            else:
                duration = audio_total_length_seconds - result[i]['start']
            assert(duration > 0)
            result[i]['duration'] = duration
            text_file.write(json.dumps(result[i], ensure_ascii=False) + '\n')
        text_file.close()
    
    return result

def transcribe_using_detection(detection_result_path, transcription_out_path, model, audio_path):
    """
    Transcribe the audio using 
    detection_result_path: File containing dicts of the following format: {start:float, duration_seconds:float, language:string}
    """
    print("transcribing " + audio_path)
    if not os.path.exists(detection_result_path):
        language_detection_test(detection_result_path, model, audio_path)
    res = open(detection_result_path).readlines()
    args = dict()
    transcription_results = []
    for line in res:
        lang_section = json.loads(line)
        start = float(lang_section['start'])
        duration = float(lang_section['duration'])
        args['language'] = re.sub(r'\s','',lang_section['lang'])
        if args['language'] == 'nil':
            continue
        transcriptions = whisper.transcribe(
            model,
            str(audio_path),
            logprob_threshold=-1.0,
            start_second = start,
            duration_seconds = duration,
            **args,
        )['segments']
        for transcription in transcriptions:
            transcription_results.append({'start': start + float(transcription['start']), 'end': start + float(transcription['end']), 'text': transcription['text'], 'lang': args['language']})
        
    print("Saving transcription to " + transcription_out_path)
    with open(transcription_out_path, "w+", encoding='UTF-8') as text_file:
        for i in range(len(transcription_results)):
            text_file.write(json.dumps(transcription_results[i], ensure_ascii=False) + '\n')
    text_file.close()
    
    return transcription_results

def transcribe_timestamp(model, audio_path, languages, out_path='out/test_transription.txt'):
    for i in range(len(languages)):
        language = languages[i]
        args = dict()
        if (language != ''):
            args['language'] = language
            print("Transcribing for language " + language + "...")
        else:
            print("Transcribing for auto detected language...")
        
        result = model.transcribe(
            str(audio_path),
            **args,
        )
                
        if (out_path != None):
            lang_marker = '_' + language if language else ''
            with open(os.path.splitext(out_path)[0] + lang_marker + '.txt', "w+", encoding='UTF-8') as text_file:
                for j in range(len(result['segments'])):
                    segment = result['segments'][j]
                    filtered_segment = {key: segment[key] for key in segment.keys() & {'start', 'end', 'text'}}
                    text_file.write(json.dumps(filtered_segment, ensure_ascii=False) + '\n')
            text_file.close()
        return result['segments']

def transcriptions_to_srt(srt_out_path, transcriptions):
    srt_segments = []
    for i in range(len(transcriptions)):
        segment = transcriptions[i]
        segment_id = i + 1
        text = segment['text']
        
        # A bit of a hack, but make sure that the end time of this segment is at least 1 milliseconds less than the
        # beginning of the next segment. Otherwise premiere pro will combine them.
        if (i != len(transcriptions) - 1 and segment['end'] >= transcriptions[i+1]['start']):
            segment['end'] = transcriptions[i+1]['start'] - 0.001
        
        startTime = str(0)+str(timedelta(seconds=int(segment['start'])))+ ',' + '{0:.3f}'.format(segment['start']).split('.')[1][:3]
        endTime = str(0)+str(timedelta(seconds=int(segment['end'])))+ ',' + '{0:.3f}'.format(segment['end']).split('.')[1][:3]
        srt_segments.append(f"{segment_id}\n{startTime} --> {endTime}\n{text[1:] if text[0] == ' ' else text}\n\n")
    print("Saving srt file of transcription to " + srt_out_path)
    with open(srt_out_path, "w+", encoding='UTF-8') as srt_file:
        for srt_segment in srt_segments:
            srt_file.write(srt_segment)
    srt_file.close()
    
def process_file(file, out_basedir, vad_model, get_speech_timestamps, whisper_model, args):
    footage_audio = ""
    if (file.endswith('.mp4')):
        # First, find if there is already an audio file corresponding to this video.
        footage_audio = os.path.join(out_basedir, os.path.basename(file).split('.')[0] + ".mp3")
        if (not os.path.isfile(footage_audio)):
            print("Extracting audio for " + file)
            mp.VideoFileClip(file).audio.write_audiofile(footage_audio)
    elif (file.endswith('.wav') or file.endswith('.mp3')):
        footage_audio = file
    else:
        sys.exit("Input file " + file + " is neither a video or an audio file.")
    
    vad_path = os.path.join(out_basedir, os.path.basename(file).split('.')[0] + "_vad.txt")
    pre_transcribe_segments = []
    if (not os.path.isfile(vad_path) or args.reprocess_vad):
        pre_transcribe_segments = vad_transcribe_timestamps(vad_model, get_speech_timestamps, footage_audio, 0.0, librosa.get_duration(filename=footage_audio), out_path=vad_path)
    else:
        print("Existing VAD found. Skipping step.")
        pre_transcribe_segments = [json.loads(f) for f in open(vad_path).readlines()]
    detection_result_path = os.path.join(out_basedir, os.path.basename(file).split('.')[0] + "_lang_detection.txt")
    if (not os.path.isfile(detection_result_path) or args.reprocess_lang_detection):
        language_detection_test(detection_result_path, whisper_model, footage_audio, pre_transcribe_segments=pre_transcribe_segments)
    else:
        print("Existing lang detection found. Skipping step.")
    transcription_out_path = os.path.join(out_basedir, os.path.basename(file).split('.')[0] + "_transcription.txt")
    if (not os.path.isfile(transcription_out_path) or args.reprocess_transcription):
        transcriptions = transcribe_using_detection(detection_result_path, transcription_out_path, whisper_model, footage_audio)
    else:
        print("Existing transcription found. Skipping step.")
        transcriptions = [json.loads(f) for f in open(transcription_out_path, encoding='utf-8').readlines()]
    if (args.output_srt):
        srt_out_path = os.path.join(out_basedir, os.path.basename(file).split('.')[0] + "_transcription.srt")
        transcriptions_to_srt(srt_out_path, transcriptions)

def walk_footage_dir(footage_dir, args):
    vad_model, get_speech_timestamps = create_vad_model()
    
    modeltype = 'medium'
    print("Loading langauge model " + modeltype + "...")
    whisper_model = whisper.load_model(modeltype)
    
    subfolders = [f.path for f in os.scandir(footage_dir) if f.is_dir()]
    for subfolder in subfolders:
        footages = [f.path for f in os.scandir(subfolder) if f.name.endswith('.mp4')]
        for footage in footages:
            process_file(footage, subfolder, vad_model, get_speech_timestamps, whisper_model, args)
                

# These VAD loading scripts are taken from aadnk/whisper-webui

def create_vad_model():
    model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad')
    
    # Silero does not benefit from multi-threading
    torch.set_num_threads(1) # JIT
    (get_speech_timestamps, _, _, _, _) = utils

    return model, get_speech_timestamps

def multiply_timestamps( timestamps: List[Dict[str, Any]], factor: float):
        result = []

        for entry in timestamps:
            start = entry['start']
            end = entry['end']

            result.append({
                'start': start * factor,
                'end': end * factor
            })
        return result

def adjust_timestamp(segments: Iterator[dict], adjust_seconds: float, max_source_time: float = None):
    result = []

    for segment in segments:
        segment_start = float(segment['start'])
        segment_end = float(segment['end'])

        # Filter segments?
        if (max_source_time is not None):
            if (segment_start > max_source_time):
                continue
            segment_end = min(max_source_time, segment_end)

            new_segment = segment.copy()

        # Add to start and end
        new_segment['start'] = segment_start + adjust_seconds
        new_segment['end'] = segment_end + adjust_seconds
        result.append(new_segment)
    return result

def load_audio(file: str, sample_rate: int = 16000, 
               start_time: str = None, duration: str = None):
    """
    Open an audio file and read as mono waveform, resampling as necessary
    Parameters
    ----------
    file: str
        The audio file to open
    sr: int
        The sample rate to resample the audio if necessary
    start_time: str
        The start time, using the standard FFMPEG time duration syntax, or None to disable.
    
    duration: str
        The duration, using the standard FFMPEG time duration syntax, or None to disable.
    Returns
    -------
    A NumPy array containing the audio waveform, in float32 dtype.
    """
    try:
        inputArgs = {'threads': 0}

        if (start_time is not None):
            inputArgs['ss'] = start_time
        if (duration is not None):
            inputArgs['t'] = duration

        # This launches a subprocess to decode audio while down-mixing and resampling as necessary.
        # Requires the ffmpeg CLI and `ffmpeg-python` package to be installed.
        out, _ = (
            ffmpeg.input(file, **inputArgs)
            .output("-", format="s16le", acodec="pcm_s16le", ac=1, ar=sample_rate)
            .run(cmd="ffmpeg", capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as e:
        raise RuntimeError(f"Failed to load audio: {e.stderr.decode()}")

    return np.frombuffer(out, np.int16).flatten().astype(np.float32) / 32768.0

def vad_transcribe_timestamps(model, get_speech_timestamps, audio: str, start_time: float, end_time: float, out_path=None):
    result = []

    # Divide procesisng of audio into chunks
    chunk_start = start_time
    VAD_MAX_PROCESSING_CHUNK = 60 * 60 # 60 minutes of audio
    SPEECH_TRESHOLD = 0.5
    while (chunk_start < end_time):
        chunk_duration = min(end_time - chunk_start, VAD_MAX_PROCESSING_CHUNK)

        sampling_rate = 16000
        wav = load_audio(audio, sampling_rate, str(chunk_start), str(chunk_duration)) 

        sample_timestamps = get_speech_timestamps(wav, model, sampling_rate=sampling_rate, threshold=SPEECH_TRESHOLD)
        seconds_timestamps = multiply_timestamps(sample_timestamps, factor=1 / sampling_rate) 
        adjusted = adjust_timestamp(seconds_timestamps, adjust_seconds=chunk_start, max_source_time=chunk_start + chunk_duration)

        result.extend(adjusted)
        chunk_start += chunk_duration
        
    i = 0
    while i < len(result):
        # If the gap between this and the next segment is less than pad_between_segments * 2, just combine them.
        if (i != len(result) - 1 and result[i+1]['start'] - result[i]['end'] < 2 * VAD_SEGMENT_PAD):
            result[i]['end'] = result[i+1]['end']
            del result[i+1] 
        else:
            i += 1

    if (out_path != None):
        with open(out_path, "w+", encoding='UTF-8') as text_file:
            for segment in result:
                text_file.write(json.dumps(segment, ensure_ascii=False) + '\n')
        text_file.close()

    return result
    

#directory paths 
parser = argparse.ArgumentParser(description='Script for organizing footage to folders.')
parser.add_argument("--footage_dir", help="Root directory for footages.")
parser.add_argument("--output_srt", action='store_true', help="Whether to also output the transcription result to an srt format.")
parser.add_argument("--test_single_file", help = "Test transcribing only for a single file.")
parser.add_argument("--reprocess_vad", action='store_true', help = "Reprocess vad even if there are existing intermediate output files.")
parser.add_argument("--reprocess_lang_detection", action='store_true', help = "Reprocess language detection even if there are existing intermediate output files.")
parser.add_argument("--reprocess_transcription", action='store_true', help = "Reprocess transcription even if there are existing intermediate output files.")
parser.add_argument("--reprocess_all", action='store_true', help = "Reprocess the entire pipeline even if there are existing intermediate output files.")

args = parser.parse_args()
if args.reprocess_all:
    args.reprocess_vad = True
    args.reprocess_lang_detection = True
    args.reprocess_transcription = True

if args.footage_dir:
    walk_footage_dir(os.path.abspath(args.footage_dir), args)

if args.test_single_file:
    filepath = os.path.abspath(args.test_single_file)
    vad_model, get_speech_timestamps = create_vad_model()
    #pre_transcribe_segments = vad_transcribe_timestamps(vad_model, get_speech_timestamps, filepath, 0.0, librosa.get_duration(filename=filepath))
    
    modeltype = 'medium'
    print("Loading langauge model " + modeltype + "...")
    
    whisper_model = whisper.load_model(modeltype)
    
    process_file(filepath, os.path.abspath('./out'), vad_model, get_speech_timestamps, whisper_model, args)
    
    
    # detection_result_name = os.path.join(os.path.abspath('./out'),  os.path.basename(filepath).split('.')[0] + "_" + 'lang_detection' + ".txt")
    # #language_detection_test(detection_result_name, model, filepath, pre_transcribe_segments = pre_transcribe_segments)
    # transcription_out_path = os.path.join(os.path.abspath('./out'),  os.path.basename(filepath).split('.')[0] + "_" + 'transcription' + ".txt")
    # #transcriptions = transcribe_using_detection(detection_result_name, transcription_out_path, model, filepath)
    # if (args.output_srt):
    #     transcriptions = [json.loads(f) for f in open(transcription_out_path, encoding='utf-8').readlines()]
    #     srt_out_path = os.path.join(os.path.abspath('./out'),  os.path.basename(filepath).split('.')[0] + "_" + 'transcription_srt' + ".txt")
    #     transcriptions_to_srt(srt_out_path, transcriptions)