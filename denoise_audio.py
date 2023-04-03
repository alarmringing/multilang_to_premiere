import torch
import torchaudio
import os
import sys
import argparse
import numpy as np
from df.enhance import enhance, init_df, load_audio, save_audio
from pydub import AudioSegment
import subprocess

MINUTE = 1000 * 60

"""
Denoises audio files.
"""

def denoise_file(model, df_state, filepath, reprocess = False, generate_mono = False):
    print("Denoising", filepath)
    audio_format = filepath.split('.')[1]
    denoised_filepath = os.path.splitext(filepath)[0] + '_denoised.' + audio_format   
        
    if (not reprocess):
        if os.path.exists(denoised_filepath):
            print('Skipping ' + os.path.basename(filepath) + '. Denoised file already exists. use --reprocess flag to reprocess.')
    
    else:
        file_to_enhance = filepath
        og_audio = AudioSegment.from_file(filepath, format=audio_format)
        
        # VERY HACKY WAY to avoid gpu out of memory issue. Need to properly support batching, but that isn't done yet.
        if (len(og_audio) > 5 * MINUTE):
            print("Skipping this file; Currently audio over 5 minutes are unsupported due to insufficient GPU memory.")
            return
        
        if (audio_format != 'wav'):        
            file_to_enhance = "original_intermediate.wav"
            og_audio.export(file_to_enhance, format="wav")
        
        audio, _ = load_audio(file_to_enhance, sr=df_state.sr())
        # Denoise the audio
        enhanced = enhance(model, df_state, audio)
        
        intermediate_enhanced = 'enhanced_intermediate.wav'
        
        # First, save to an intermediate wav file without compressing or adjusting for framerate.
        save_audio(intermediate_enhanced, enhanced, df_state.sr())
        enhanced_audio = AudioSegment.from_file(intermediate_enhanced, format='wav')
        
        # Make sure output audio has the same frame rate as the original audio.
        enhanced_audio.set_frame_rate(og_audio.frame_rate)
        enhanced_audio.export(denoised_filepath, format=audio_format)
    
    if (generate_mono):
        # Now make a mono version.
        denoised_mono_filepath = os.path.splitext(filepath)[0] + '_denoised_mono.' + audio_format  
        cmd_str = "ffmpeg -y -i " + denoised_filepath + " -ac 1 "  + denoised_mono_filepath
        subprocess.run(cmd_str, shell=True)

    print("Saved denoised file to ", denoised_filepath)

if __name__ == "__main__":
    #directory paths 
    parser = argparse.ArgumentParser(description='Script for organizing footage to folders.')
    parser.add_argument("--dir", help="If set, would run denoising on all audio under this directory recursively.")
    parser.add_argument("--test_single_file", help = "Test denoising only a single audio file.")
    parser.add_argument("--reprocess", action='store_true', help = "Reprocess audio to denoise even if a denoised file exists.")
    parser.add_argument("--generate_mono", action='store_true', help = "Generate mono versions of the denoised audio.")
    
    args = parser.parse_args()

    model, df_state, _ = init_df(post_filter=True, config_allow_defaults=True)  # Load default model
        
    if args.dir:
        if not os.path.exists(args.dir):
            sys.exit(args.dir + " is an invalid directory. Exiting.")
        
        for root, dirs, files in os.walk(args.dir):
            path = root.split(os.sep)
            for file in files:
                if file.split('.')[0].endswith('denoised'):
                    continue
                if file.endswith('wav') or file.endswith('.mp3'):
                    denoise_file(model, df_state, os.path.join(root, file), args.reprocess, generate_mono = args.generate_mono)

    if args.test_single_file:
        filepath = os.path.abspath(args.test_single_file)
        denoise_file(model, df_state, filepath, args.reprocess, generate_mono = args.generate_mono)
        