import os
import sys
import json
import argparse
import pysrt
import pymiere
from datetime import timedelta
from pymiere.wrappers import time_from_seconds
from transcription import transcriptions_to_srt

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

def transcribe_sequence(sequence, reprocess=False):
    srt_outpath = os.path.join(footage_dir, sequence.name, sequence.name + '_multilang_captions.srt')
    
    if os.path.isfile(srt_outpath) and not reprocess:
        print("Srt file for " + sequence.name + " already exists. Skipping processing. Set --reprocess flag to reprocess existing srt files.")
        return
    
    if not os.path.isdir(os.path.dirname(srt_outpath)):
        new_dir = os.path.dirname(srt_outpath)
        print("{new_dir} doesn't exist. Creating the directory.")
        os.mkdir(new_dir)
    
    print("Transcribing sequence " + sequence.name + "...")
    pymiere.objects.app.project.openSequence(sequenceID=sequence.sequenceID)
    captions = []
    
    # Current position of this clip in this track. Increment after each clip.
    clip_begin_time_in_track = 0.0
    for clip in project.activeSequence.videoTracks[0].clips:
        mediapath = clip.projectItem.getMediaPath()
        if not os.path.isfile(mediapath):
            print("Skipping {sequence.name} because path to the clip in track is not a valid path. path: " + mediapath)
            continue
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
    transcriptions_to_srt(srt_outpath, captions)

def add_text_graphic_to_sequence(sequence, footage_dir, mgt_dir):    
    print("Adding graphics for text in sequence " + sequence.name + "...")
    pymiere.objects.app.project.openSequence(sequenceID=sequence.sequenceID)
    sequence_dir = os.path.join(footage_dir, sequence.name)
    languages = ['en', 'ko', 'ja', 'zh']
    text_track_start_point = len(sequence.videoTracks) - len(languages)
    
    for i in range(len(languages)):
        lang = languages[i]
        print("lang: ", lang)
        # Caption .srt file is assumed to be in the directory of sequence's footages, with the format of ($SEQUENCENAME)_multilang_final_($lang).srt
        srt_path = os.path.join(sequence_dir, sequence.name + '_multilang_final_' + lang + '.srt')
        if not os.path.isfile(srt_path):
            print("Skip processing language " + lang + "; can't find the caption file. It should be in the format of ($SEQUENCENAME)_multilang_final_($lang).srt")
            continue 
        captions = pysrt.open(srt_path)
        # Motion graphics template is assumed to be in mgt_dir with the file name as ($lang).mogrt
        mogrt_path = os.path.join(mgt_dir, lang + '_title.mogrt')
        if not os.path.isfile(mogrt_path):
            print("Skip processing language " + lang + "; can't find .mogrt file.")
            continue 
        for caption in captions:
            caption_start_time = caption.start.minutes * 60 + caption.start.seconds + 0.001 * caption.start.milliseconds
            mgt_clip = sequence.importMGT(  
                path=mogrt_path,  
                time=time_from_seconds(caption_start_time),  # start time  
                videoTrackIndex=text_track_start_point+i, audioTrackIndex=1  # Place this caption on a new track
            )
            mgt_clip.end = time_from_seconds(caption.end.minutes * 60 + caption.end.seconds + 0.001 * caption.end.milliseconds)
            # get component hosting modifiable template properties  
            mgt_component = mgt_clip.getMGTComponent()  
            # handle two possible types for mgt
            if mgt_component is None:
                # Premiere Pro type, directly use components
                components = mgt_clip.components
            else:
                # After Effects type, everything is hosted by the MGT component
                components = [mgt_component]
            for component in components:
                # iter through MGT properties
                for prop in component.properties:
                    #print("property name: ", prop.displayName)
                    if (prop.displayName == 'Text'):
                        prop.setValue(caption.text, True)
    
def add_denoised_audio_to_sequence(denoised_dir, sequence):
    project = pymiere.objects.app.project
    project.openSequence(sequenceID=sequence.sequenceID)
    bin = project.rootItem
    for child in project.rootItem.children:
        if child.name == "denoised_audio":
            bin = child
            break
    
    # BEWARE! Denoised audiotrack is set as the last audio track by default. This may overwrite the existing project.
    denoised_audioTrack = project.activeSequence.audioTracks[-1]
    denoised_audioTrack.setMute(1.0)
    
    # Current position of this clip in this track. Increment after each clip.
    clip_begin_time_in_track = 0.0
    for clip in project.activeSequence.audioTracks[0].clips:
        mediapath = clip.projectItem.getMediaPath()
        if not os.path.isfile(mediapath):
            print("Skipping {sequence.name} because path to the clip in track is not a valid path. path: " + mediapath)
            continue
        
        # In the same directory as mediapath, look for a denoised audio file. Assumes .mp3 for now.
        denoised_audio_filepath = os.path.join(denoised_dir, os.path.basename(mediapath).split('.')[0] + "_denoised_mono.mp3")
        if not os.path.isfile(denoised_audio_filepath):
            print("Skipping {mediapath}'s denoised audio file because it doesn't exist.")
            clip_begin_time_in_track += clip.duration.seconds
            continue
        else:
            if (len(bin.findItemsMatchingMediaPath(denoised_audio_filepath, ignoreSubclips=False)) == 0):
                success = project.importFiles(
                        [denoised_audio_filepath],
                        suppressUI=True,
                        targetBin=bin,
                        importAsNumberedStills=False
                    )

            denoised_audio_item = bin.findItemsMatchingMediaPath(denoised_audio_filepath, ignoreSubclips=False)[0]

            denoised_audioTrack.insertClip(denoised_audio_item, clip_begin_time_in_track)

            # denoised_audioTrack.clips[-1].inPoint = clip.inPoint
            # denoised_audioTrack.clips[-1].outPoint = clip.outPoint
            denoised_audioTrack.clips[-1].start = clip.start
            denoised_audioTrack.clips[-1].end = clip.end
        
            clip_begin_time_in_track += clip.duration.seconds
       
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Script for organizing footage to folders.')
    parser.add_argument("footage_dir", help="Root directory for footages.")
    parser.add_argument('--transcribe', action='store_true', help='Use this flag to transcribe a sequence.')
    parser.add_argument('--add_denoised_audio_dir', help='Set a directory of denoised audio fiels to add denoised audio on a sequence.')
    parser.add_argument('--add_text_with_mgt_dir', help='Add text graphics in 4 languages for a sequence with the mgt file templates in this directory.')
    parser.add_argument('--premiere_project_path',
                        help="Path for premiere project to use. Otherwise, will use the first found one in the footage directory.")
    parser.add_argument('--sequence_name',
                        help="Name of the sequence to generate subtitles for. If not set, script will attempt to generate script for all sequences in the project.")
    parser.add_argument('--reprocess', action='store_true', help='Whether to regenerate srt files even if there is already an existing oen for the sequence.')

    args = parser.parse_args()
    
    if (not (args.transcribe or args.add_denoised_audio_dir or args.add_text_with_mgt_dir)):
        sys.exit("Must specify --transcribe, --add_denoised_audio, or --add_text_with_mgt_dir flag! Use -h for help.")

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
        if (args.transcribe):
            transcribe_sequence(sequence, reprocess=args.reprocess)  
        if (args.add_denoised_audio_dir):
            add_denoised_audio_to_sequence(args.add_denoised_audio_dir, sequence)
        if (args.add_text_with_mgt_dir):
            add_text_graphic_to_sequence(sequence, footage_dir, args.add_text_with_mgt_dir)
    else:
        # open each sequence and run process_sequence.
        for sequence in pymiere.objects.app.project.sequences:
            if (args.transcribe):
                transcribe_sequence(sequence, reprocess=args.reprocess)
            if (args.add_denoised_audio_dir):
                add_denoised_audio_to_sequence(args.add_denoised_audio_dir, sequence)