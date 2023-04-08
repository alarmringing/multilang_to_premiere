import os
import sys
import json
import argparse
import pysrt
import html
from google.cloud import translate
from google.cloud.translate_v3.types import translation_service
from google.oauth2 import service_account

# Maximum amount of lines possible to send in a single translation request.
MAX_STRING_LIMIT = 1000

def generate_stats(response_from_translate_api, captions):
    language_durations = {'ko':0.0, 'en':0.0, 'zh':0.0, 'ja':0.0}
    total_speech_duration = 0.0
    for i in range(len(response_from_translate_api)):
        language = response_from_translate_api[i].languages[0].language_code
        if (language == 'zh-CN' or language == 'zh-TW'):
            language = 'zh'
        if language not in ['ko', 'zh', 'en', 'ja']:
            continue
        duration = (captions[i].end - captions[i].start).seconds + 0.001 * (captions[i].end - captions[i].start).milliseconds
        total_speech_duration += duration
        language_durations[language] += duration
    print("total_speech_duration is ", total_speech_duration)
    for lang in language_durations:
        print("Language", lang, " percentage: ", float(language_durations[lang]) / float(total_speech_duration))

def translate_captions(srt_path, google_api_key_path, args):
    
    captions = pysrt.open(srt_path)
        
    credentials = service_account.Credentials.from_service_account_file(google_api_key_path)
    client = translate.TranslationServiceClient(credentials=credentials)
    project_id = credentials.project_id
    assert(project_id)
    location = 'global'
    parent = f'projects/{project_id}/locations/{location}'
    
    if (args.stats and not (args.english and args.four_languages)):
        print("Only running language detection model.")
        response = []
        for caption in captions:
            response.append(client.detect_language(content=caption.text, parent=parent))
        generate_stats(response, captions)
        return
   
    translation_target_languages = []
    if (args.english):
        translation_target_languages = ['en']
    if (args.four_languages):
        translation_target_languages = ['en', 'ja', 'ko', 'zh-CN']
        
    for target_language in translation_target_languages:
        print("Translating " + srt_path + " to " + target_language + "...")
        translated_captions = []
        for k in range(len(captions) // MAX_STRING_LIMIT + 1):
            captions_batch = captions[k * MAX_STRING_LIMIT:k * MAX_STRING_LIMIT + min(len(captions) - k * MAX_STRING_LIMIT, MAX_STRING_LIMIT)] 
            response = client.translate_text(
                contents=[c.text for c in captions_batch],
                target_language_code=target_language,
                parent=parent,
            )
            
            if(len(response.translations) != len(captions_batch)):
                sys.exit("Error: length of translated results does not match the length of captions.")                
            
            for i in range(len(response.translations)):
                text = html.unescape(response.translations[i].translated_text)
                this_caption = captions[i + k * MAX_STRING_LIMIT]
                translated_caption = pysrt.SubRipItem(this_caption.index, this_caption.start, this_caption.end, text, this_caption.position)
                translated_captions.append(translated_caption)
        
        if target_language == 'zh-CN':
            target_language = 'zn'
        translated_srt_outpath = os.path.join(os.path.dirname(srt_path), os.path.basename(srt_path).split('.')[0] + '_' + target_language + '.srt')
        pysrt.SubRipFile(translated_captions).save(translated_srt_outpath, encoding='utf-8')
        print("Translated captions outputted to ", translated_srt_outpath)

parser = argparse.ArgumentParser(
    description='Generate subtitles in 4 languages given an input srt file in multi-language format.')
parser.add_argument("srt_path", help="Path to the srt caption file to process.")
parser.add_argument('google_api_key_path',
                    help="Path to the key to use for google translate api. Otherwise translation is not possible.")
parser.add_argument('--english', action='store_true', help="Translate for english only.")
parser.add_argument('--four_languages', action='store_true', help='Translate for all languages: English, Chinese, Korean, Japanese')
parser.add_argument('--stats', action='store_true', help='Return stats for percentage of each language.')

args = parser.parse_args()
srt_path = os.path.abspath(args.srt_path)
google_api_key_path = os.path.abspath(args.google_api_key_path)

if (os.path.isfile(srt_path) and srt_path.endswith('.srt') and os.path.isfile(google_api_key_path) and google_api_key_path.endswith('.json')):
    if ((args.english and args.four_languages)):
        sys.exit("Specify only one of the two flags: --english, or --four_languages.")
    translate_captions(srt_path, google_api_key_path, args)
else:
    sys.exit("Input arguments are not valid, either wrong path or file extension.")