import os
import sys
import json
import argparse
import pysrt
import html
from google.cloud import translate
from google.oauth2 import service_account

def translate_captions(srt_path, google_api_key_path):
    
    captions = pysrt.open(srt_path)
    
    credentials = service_account.Credentials.from_service_account_file(google_api_key_path)
    client = translate.TranslationServiceClient(credentials=credentials)
    
    project_id = credentials.project_id
    assert(project_id)
    location = 'global'
    
    translation_target_languages = ['en']
    
    for target_language in translation_target_languages:
        print("Translating " + srt_path + " to " + target_language + "...")
        parent = f'projects/{project_id}/locations/{location}'
        response = client.translate_text(
            contents=[caption.text for caption in captions],
            target_language_code=target_language,
            parent=parent,
        )
        
        if(len(response.translations) != len(captions)):
            sys.exit("Error: length of translated results does not match the length of captions.")
        
        translated_captions = []
        for i in range(len(response.translations)):
            text = html.unescape(response.translations[i].translated_text)
            translated_caption = pysrt.SubRipItem(captions[i].index, captions[i].start, captions[i].end, text, captions[i].position)
            translated_captions.append(translated_caption)
        
        translated_srt_outpath = os.path.join(os.path.dirname(srt_path), os.path.basename(srt_path).split('.')[0] + '_' + target_language + '.srt')
        pysrt.SubRipFile(translated_captions).save(translated_srt_outpath, encoding='utf-8')
        print("Translated captions outputted to ", translated_srt_outpath)

parser = argparse.ArgumentParser(
    description='Generate subtitles in 4 languages given an input srt file in multi-language format.')
parser.add_argument("srt_path", help="Path to the srt caption file to process.")
parser.add_argument('google_api_key_path',
                    help="Path to the key to use for google translate api. Otherwise translation is not possible.")

args = parser.parse_args()
srt_path = os.path.abspath(args.srt_path)
google_api_key_path = os.path.abspath(args.google_api_key_path)

if (os.path.isfile(srt_path) and srt_path.endswith('.srt') and os.path.isfile(google_api_key_path) and google_api_key_path.endswith('.json')):
    translate_captions(srt_path, google_api_key_path)
else:
    sys.exit("Input arguments are not valid, either wrong path or file extension.")