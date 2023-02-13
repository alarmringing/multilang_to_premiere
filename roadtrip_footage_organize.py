import os 
import datetime
import argparse
from shutil import move
#from hachoir.parser import createParser
#from hachoir.metadata import extractMetadata

def get_non_hidden_files_except_current_file(root_dir):
  return [f for f in os.listdir(root_dir) if os.path.isfile(f) and not f.startswith('.') and not f.__eq__(__file__)]

#directory paths 
parser = argparse.ArgumentParser(description='Script for organizing footage to folders.')
parser.add_argument("footage_dir", help="Root directory for footages.")
args = parser.parse_args()
footage_dir = os.path.abspath(args.footage_dir)
print("footage_dir is " +footage_dir)

files = get_non_hidden_files_except_current_file(footage_dir)
print("files is " + str([f for f in os.listdir(footage_dir)]))

for file in [f for f in os.listdir(footage_dir)]:
    fullpath = os.path.join(footage_dir, file)
    #metadata = extractMetadata(createParser(fullpath))
    # for line in metadata.exportPlaintext():
    #     if line.split(':')[0] == '- Creation date':
            #creationdate = datetime.datetime.strptime(line.split(":")[1].split()[0], "%Y-%m-%d")
            #dirname = creationdate.strftime("%m_%d_%Y")
    # This assumes YYYYMMDD format for beginning of file names. 
    dirname = file[4:6] + "_" + file[6:8] + "_" + file[0:4]
    newdir = os.path.join(footage_dir, dirname)
    if not os.path.exists(newdir):
        os.makedirs(newdir)
    print("moving " + file + " to " + os.path.join(newdir, file))
    move(fullpath, os.path.join(newdir, file))