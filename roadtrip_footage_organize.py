import os
import datetime
import sys
import argparse
from shutil import move
import pymiere
from pymiere.wrappers import get_system_sequence_presets
from pymiere.wrappers import time_from_seconds
from moviepy.editor import VideoFileClip
from datetime import timedelta


def get_non_hidden_files_except_current_file(root_dir):
    return [f for f in os.listdir(root_dir) if os.path.isfile(f) and not f.startswith('.')]


def calculate_footage_duration(footage_dir):
    subfolders = [f.path for f in os.scandir(footage_dir) if f.is_dir()]
    lines = []
    total_duration = 0
    for subfolder in subfolders:
        subfolder_duration = 0
        footages = [os.path.join(subfolder, f)
                    for f in os.listdir(subfolder) if f.endswith('.mp4')]
        for footage_path in footages:
            clip = VideoFileClip(footage_path)
            subfolder_duration += clip.duration
        sd = str(timedelta(seconds=subfolder_duration)).split(':')

        lines.append("Footage duration of " + os.path.basename(subfolder) + " is " +
                     sd[0] + ':' + sd[1] + ':' + str(int(float(sd[2]))) + '\n')
        print(lines[-1])
        total_duration += subfolder_duration

    td = str(timedelta(seconds=total_duration)).split(':')
    lines.append("Total duration of footages is " +
                 td[0] + ' Hours ' + td[1] + ' Minutes ' + str(int(float(td[2]))) + ' Seconds ' + '\n')

    print(lines[-1])
    duration_outpath = os.path.join(footage_dir, 'duration.txt')
    with open(duration_outpath, 'w+', encoding='utf-8') as duration:
        for line in lines:
            duration.write(line)
    duration.close()


def organize_footages_to_folders(footage_dir):
    for file in [f for f in os.listdir(footage_dir)]:
        fullpath = os.path.join(footage_dir, file)
        dirname = file[4:6] + "_" + file[6:8] + "_" + file[0:4]
        newdir = os.path.join(footage_dir, dirname)
        if not os.path.exists(newdir):
            os.makedirs(newdir)
        print("moving " + file + " to " + os.path.join(newdir, file))
        move(fullpath, os.path.join(newdir, file))


def generate_sequence(footage_dir):
    if not args.premiere_project_path:
        sys.exit('--premiere_project_path path is required for sequence genereation.')

    premiere_project_path = os.path.abspath(args.premiere_project_path)
    project = pymiere.objects.app.project
    # Create a new premiere project if it doesn't exist yet.
    if not os.path.isfile(premiere_project_path):
        print("Creating new premiere project for " + premiere_project_path)
        success = pymiere.objects.app.newProject(premiere_project_path)
        if not success:
            sys.exit("Failed creating a new premiere project.")

    pymiere.objects.app.openDocument(premiere_project_path)
    sequence_preset_path = get_system_sequence_presets(
        category="HDV", resolution=None, preset_name="HDV 1080p25")

    subfolders = [f.path for f in os.scandir(footage_dir) if f.is_dir()]
    for subfolder in subfolders:

        # Find or create new sequence named after the subfolder.
        sequence_name = os.path.basename(subfolder)
        sequences_with_subfolder_name = [
            s for s in pymiere.objects.app.project.sequences if s.name == sequence_name]
        if (len(sequences_with_subfolder_name) == 0):
            print("Creating new sequence for " + subfolder)
            success = pymiere.objects.qe.project.newSequence(
                sequence_name, sequence_preset_path)
            if not success:
                sys.exit("Failed creating a new premiere sequence.")
            sequences_with_subfolder_name = [
                s for s in pymiere.objects.app.project.sequences if s.name == sequence_name]

        # Find the newly created sequence.
        sequence = sequences_with_subfolder_name[0]
        pymiere.objects.app.project.openSequence(
            sequenceID=sequence.sequenceID)

        footages = [os.path.join(subfolder, f)
                    for f in os.listdir(subfolder) if f.endswith('.mp4')]
        if (len(footages) == 0):
            continue
        if (len(footages) == len(project.activeSequence.videoTracks[0].clips)):
            # All clips have already been imported. continue.
            continue

        bin = project.rootItem.createBin(sequence_name)
        if not bin:
            # Bin already exists, so find it.
            for child in project.rootItem.children:
                if child.name == sequence_name:
                    bin = child
                    break
        # Import the footages into Premiere.
        end_of_last_clip = time_from_seconds(0)
        for i in range(len(footages)):
            footage = footages[i]
            if (footage.endswith('jpg') or len(bin.findItemsMatchingMediaPath(
                    footage, ignoreSubclips=False)) > 0):
                # Footage is an image (don't place in timeline automatically), or already imported.
                continue

            success = project.importFiles(
                [footage],
                suppressUI=True,
                targetBin=bin,
                importAsNumberedStills=False
            )

            if not success:
                sys.exit("Failure importing footage at: " + subfolder)

            print("Inserting clip for " + subfolder + "...")
            premiere_footage = bin.findItemsMatchingMediaPath(
                footage, ignoreSubclips=False)[0]

            end_of_last_clip = 0
            if (i > 0):
                end_of_last_clip = project.activeSequence.videoTracks[0].clips[i-1].end.seconds
            # Add clip to active sequence.
            project.activeSequence.videoTracks[0].insertClip(
                premiere_footage, end_of_last_clip)

    pymiere.objects.app.project.closeDocument()


parser = argparse.ArgumentParser(
    description='Script for organizing footage to folders.')
parser.add_argument("footage_dir", help="Root directory for footages.")
parser.add_argument("--calculate_footage_duration", action='store_true',
                    help='Calculate the running time of all footages within this directory.')
parser.add_argument('--organize', action='store_true',
                    help="Organize the footages in this directory to folders organized by creation date.")
parser.add_argument('--generate_sequence', action='store_true',
                    help="Generate one premiere sequence out of each subfolder.")
parser.add_argument('--premiere_project_path',
                    help="Path for premiere project to use.")

args = parser.parse_args()

footage_dir = os.path.abspath(args.footage_dir)

if (args.calculate_footage_duration):
    calculate_footage_duration(footage_dir)

if (args.organize):
    organize_footages_to_folders(footage_dir)

if (args.generate_sequence):
    generate_sequence(footage_dir)
