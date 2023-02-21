import os
import sys
import json
import argparse
import pymiere
from datetime import timedelta

def captions_to_srt(srt_outpath, captions):
    print("Outputting captions to srt file at " + srt_outpath)
    srt_segments = []
    for i in range(len(captions)):
        segment = captions[i]
        segment_id = i + 1
        text = segment['text']
        startTime = str(0)+str(timedelta(seconds=int(segment['start']))) + ',' + '{0:.3f}'.format(segment['start']).split('.')[1][:3]
        endTime = str(0)+str(timedelta(seconds=int(segment['end']))) + ',' + '{0:.3f}'.format(segment['end']).split('.')[1][:3]
        srt_segments.append(f"{segment_id}\n{startTime} --> {endTime}\n{text[1:] if text[0] == ' ' else text}\n\n")
    with open(srt_outpath, 'w+', encoding='utf-8') as srtFile:
        for srt_segment in srt_segments:
            srtFile.write(srt_segment)
        srtFile.close()

def add_transcription_to_captions(trackItem, clip_begin_time_in_track, transcription_path, captions):
    transcribe_segments = [json.loads(f) for f in open(transcription_path, encoding='utf-8').readlines()]
    for segment in transcribe_segments:
        # Filter out segments that fall outside the inPoint-outPoint range of this trackItem.
        if (segment['end'] < trackItem.inPoint.seconds):
            continue
        elif (segment['start'] > trackItem.outPoint.seconds):
            break
        
        segment['text'] = segment['text'].strip()
        # This is totally a hack, but Whisper 'hallucinates' so much false instances of Thanks for watching! that
        # if we run into one, it's guaranteed to be a wrong transcription. Besides it belongs only in an end of the video anyway.
        if (segment['text'] == 'Thanks for watching!'):
            continue
        start_in_sequence = clip_begin_time_in_track + max(0.0, segment['start'] - trackItem.inPoint.seconds)
        end_in_sequence =  clip_begin_time_in_track + min(trackItem.duration.seconds, segment['end'] - trackItem.inPoint.seconds)
        captions.append({'start': start_in_sequence, 'end': end_in_sequence, 'text': segment['text']})

def process_sequence(sequence, reprocess=False):
    
    srt_outpath = os.path.join(footage_dir, sequence.name, sequence.name + '_multilang_captions.srt')
    if os.path.isfile(srt_outpath) and not reprocess:
        print("Srt file for " + sequence.name + " already exists. Skipping processing. Set --reprocess flag to reprocess existing srt files.")
        return
    
    print("Processing sequence " + sequence.name + "...")
    pymiere.objects.app.project.openSequence(sequenceID=sequence.sequenceID)
    captions = []
    
    # Current position of this clip in this track. Increment after each clip.
    clip_begin_time_in_track = 0.0
    for clip in project.activeSequence.videoTracks[0].clips:
        mediapath = clip.projectItem.getMediaPath()
        if not os.path.isfile(mediapath):
            sys.exit("Path to the clip in track is not a valid path. path: " + mediapath)
        # In the same directory as mediapath, look for a transcription file.
        parent_dir = os.path.dirname(mediapath)
        transcription_file_name = os.path.basename(mediapath).split('.')[0] + "_transcription.txt"
        transcription_path = ""
        for file in [f.path for f in os.scandir(parent_dir)]:
            if (os.path.basename(file) == transcription_file_name):
                transcription_path = file
                # Transcription for this clip was found.
                add_transcription_to_captions(clip, clip_begin_time_in_track, transcription_path, captions)
                break
        clip_begin_time_in_track += clip.duration.seconds
    captions_to_srt(srt_outpath, captions)
       

parser = argparse.ArgumentParser(
    description='Script for organizing footage to folders.')
parser.add_argument("footage_dir", help="Root directory for footages.")
parser.add_argument('--premiere_project_path',
                    help="Path for premiere project to use. Otherwise, will use the first found one in the footage directory.")
parser.add_argument('--sequence_name',
                    help="Name of the sequence to generate subtitles for. If not set, script will attempt to generate script for all sequences in the project.")
parser.add_argument('--reprocess', action='store_true', help='Whether to regenerate srt files even if there is already an existing oen for the sequence.')

args = parser.parse_args()

footage_dir = os.path.abspath(args.footage_dir)
premiere_project_path = ""
if (args.premiere_project_path):  
    premiere_project_path = args.premiere_project_path
else:
    for file in [f for f in os.scandir(footage_dir)]:
        if file.name.endswith('.prproj'):
            premiere_project_path = file.path
            break
    if premiere_project_path == "":
        sys.exit("Cannot find a premiere project to open.")

print("Opening project " + premiere_project_path)
project = pymiere.objects.app.project
pymiere.objects.app.openDocument(premiere_project_path)

if args.sequence_name:
    sequences_with_subfolder_name = [s for s in pymiere.objects.app.project.sequences if s.name == args.sequence_name]
    if len(sequences_with_subfolder_name) == 0:
        sys.exit("Sequence with " + args.sequence_name + " could not be found.")
    elif len(sequences_with_subfolder_name) > 1:
        sys.exit("More than one sequence with the name " + args.sequence_name + " was found.")

    sequence = sequences_with_subfolder_name[0]
    process_sequence(sequence, reprocess=args.reprocess)  
else:
    # open each sequence and run process_sequence.
    for sequence in pymiere.objects.app.project.sequences:
        process_sequence(sequence)