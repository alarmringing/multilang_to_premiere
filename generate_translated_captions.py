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
MAX_STRING_LIMIT = 700

def modified_path(path, end, ext):
    return os.path.join(os.path.dirname(path), os.path.basename(path).split('.')[0] + '_' + end + '.' + ext)

def read_languages(srt_path):
    if not os.path.isfile(modified_path(srt_path, 'languages', 'txt')):
        print('The language detection file for ' + srt_path + ' does not exist.')
        return []
    file = open(modified_path(srt_path, 'languages', 'txt'), "r", encoding='UTF-8')
    return [r.strip() for r in file.readlines()]

def generate_stats(languages, captions):
    language_durations = {'ko':0.0, 'en':0.0, 'zh':0.0, 'ja':0.0}
    total_speech_duration = 0.0
    for i in range(len(languages)):
        language = languages[i]
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
    
    if (args.stats):
        languages = read_languages(srt_path)
        
        if len(languages) != len(captions):
            print ("Number of languages detected in _languages.txt does not match length of captions! Regenerating language file..")
        
        if len(languages) == 0:
            print("Running language detection model.")
            response = []
            for caption in captions:
                response.append(client.detect_language(content=caption.text, parent=parent))
            for i in range(len(response)):
                languages.append(response[i].languages[0].language_code)
            if len(languages) > 0:
                file = open(modified_path(srt_path, 'languages', 'txt'), "w+", encoding='UTF-8')
                file.writelines([r + '\n' for r in languages])
        
        generate_stats(languages, captions)
        return
   
    translation_target_languages = []
    if (args.en):
        translation_target_languages = ['en']
    if (args.ko_en):
        translation_target_languages = ['en', 'ko']
    if (args.four_languages):
        translation_target_languages = ['en', 'ja', 'ko', 'zh-CN']
    if (args.ja_zh):
        translation_target_languages = ['ja', 'zh-CN']
        
        
    for l in range(len(translation_target_languages)):
        target_language = translation_target_languages[l]
        print("Translating " + srt_path + " to " + target_language + "...")
        
        if(args.ja_zh):
            languages = read_languages(srt_path)
            print("result from read languages: ", languages)
            # Experimental Split transate - translate japanese from korean, and chinese from english.
            # Assumes srt path for english and korean translations already exist.
            translated_srt_path = ""
            if target_language == 'ja':
                translated_srt_path =  modified_path(srt_path, 'ko', 'srt')
            if target_language == 'zh-CN':
                translated_srt_path =   modified_path(srt_path, 'en', 'srt')
            if not os.path.isfile(translated_srt_path):
                sys.exit('For experimental two-step translation, a base translation file is necessary. Missing: ', os.path.basename(base_translated_captions))
            base_translated_captions = pysrt.open(translated_srt_path)
            if len(captions) != len(base_translated_captions):
                sys.exit("Number of captions in " + os.path.basename(srt_path) + ' and ' + os.path.basename(base_translated_captions) + ' must match.')
            for i in range(len(captions)):
                # Replace the original captions with the base translated language, unless the original caption is
                # already in the target language.
                if languages[i][0:2] != target_language:
                    captions[i] = base_translated_captions[i]
        
        translated_captions = []
        detected_languages = []
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
                if (not os.path.isfile(modified_path(srt_path, 'languages', 'txt')) and l == 0):
                    detected_languages.append(response.translations[i].detected_language_code)
        
        if target_language == 'zh-CN':
            target_language = 'zh'
        
        # Output translated captions.    
        translated_srt_outpath =  modified_path(srt_path, target_language, 'srt')
        pysrt.SubRipFile(translated_captions).save(translated_srt_outpath, encoding='utf-8')
        print("Translated captions outputted to ", translated_srt_outpath)
        
        # If first language to be translated, then also output language detection result.
        if len(detected_languages) > 0:
            file = open(modified_path(srt_path, 'languages', 'txt'), "w+", encoding='UTF-8')
            file.writelines([r + '\n' for r in detected_languages])

parser = argparse.ArgumentParser(
    description='Generate subtitles in 4 languages given an input srt file in multi-language format.')
parser.add_argument("srt_path", help="Path to the srt caption file to process.")
parser.add_argument('google_api_key_path',
                    help="Path to the key to use for google translate api. Otherwise translation is not possible.")
parser.add_argument('--en', action='store_true', help="Translate for english only.")
parser.add_argument('--ko_en', action = 'store_true', help='Experimental: Step one of split translate. Translate only korean and english.')
parser.add_argument('--ja_zh', action = 'store_true', help='Experimental: Step two of split translate. Translate only japanese and chinese based on english and korean translations.')
parser.add_argument('--four_languages', action='store_true', help='Translate for all languages: English, Chinese, Korean, Japanese')
parser.add_argument('--stats', action='store_true', help='Return stats for percentage of each language.')

args = parser.parse_args()
srt_path = os.path.abspath(args.srt_path)
google_api_key_path = os.path.abspath(args.google_api_key_path)

if (os.path.isfile(srt_path) and srt_path.endswith('.srt') and os.path.isfile(google_api_key_path) and google_api_key_path.endswith('.json')):
    print("Translating captions..")
    if (list(map(bool, [args.en, args.ko_en, args.ja_zh, args.four_languages, args.stats])).count(True) != 1):
        sys.exit("Specify one of available flags. Use --help to see options.")
    translate_captions(srt_path, google_api_key_path, args)
else:
    sys.exit("Input arguments are not valid, either wrong path or file extension.")