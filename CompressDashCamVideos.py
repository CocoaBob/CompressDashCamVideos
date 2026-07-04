import argparse
import datetime
import json
import logging
import os
import shutil
import subprocess
import tempfile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def getDatetime(dtStr, model):
    if model == "d5": # YYYY_MMDD_HHMMSS_00_a/b.mp4
        components = dtStr.split("_") # Date time conponents
        return datetime.datetime(int(components[0]), # Year
                                int(components[1][:2]), # Month
                                int(components[1][-2:]), # Day
                                int(components[2][:2]), # Hour
                                int(components[2][2:4]), # Minute
                                int(components[2][-2:])) # Second
    elif model == "s80wifi": # YYYY_MMDD_HHMMSS_123A/B.mp4
        components = dtStr.split("_") # Date time conponents
        return datetime.datetime(int(components[0]), # Year
                                int(components[1][:2]), # Month
                                int(components[1][-2:]), # Day
                                int(components[2][:2]), # Hour
                                int(components[2][2:4]), # Minute
                                int(components[2][-2:])) # Second
    elif model == "s36": # YYYY-MM-DD-HH-MM-SS.MOV
        components = dtStr.split("-") # Date time conponents
        return datetime.datetime(int(components[0]), # Year
                                int(components[1]), # Month
                                int(components[2]), # Day
                                int(components[3]), # Hour
                                int(components[4]), # Minute
                                int(components[5][:2])) # Second
    elif model == "fitcamx": # YYYYMMDDHHMMSS_000001A/B.TS
        digits = "".join(filter(str.isdigit, dtStr))
        return datetime.datetime.strptime(digits[:14], "%Y%m%d%H%M%S")

def getFitcamxOutputPrefix(filename):
    dtRaw = filename.split("_")[0]
    return dtRaw[:4] + "_" + dtRaw[4:8] + "_" + dtRaw[8:14]

def getD5OutputPrefix(filename):
    components = filename.split("_")
    if len(components) >= 3:
        return components[0] + "_" + components[1] + "_" + components[2]
    return filename

def moveFitcamxEmrToMovie(cardvDir):
    emrDir = os.path.join(cardvDir, "EMR")
    movieDir = os.path.join(cardvDir, "Movie")
    if os.path.isdir(emrDir) and os.path.isdir(movieDir):
        emrFiles = filenamesInDir(emrDir)
        if len(emrFiles) > 0:
            logging.info("Moving EMR files to Movie...")
            for filename in emrFiles:
                src = os.path.join(emrDir, filename)
                dst = os.path.join(movieDir, filename)
                if os.path.exists(dst):
                    logging.info("Skip existing file in Movie: " + dst)
                    continue
                shutil.move(src, dst)

    emrEDir = os.path.join(cardvDir, "EMR_E")
    movieEDir = os.path.join(cardvDir, "Movie_E")
    if os.path.isdir(emrEDir) and os.path.isdir(movieEDir):
        emrEFiles = filenamesInDir(emrEDir)
        if len(emrEFiles) > 0:
            logging.info("Moving EMR_E files to Movie_E...")
            for filename in emrEFiles:
                src = os.path.join(emrEDir, filename)
                dst = os.path.join(movieEDir, filename)
                if os.path.exists(dst):
                    logging.info("Skip existing file in Movie_E: " + dst)
                    continue
                shutil.move(src, dst)

def getVideoWidth(path):
    command = "ffmpeg -i " + path + " 2>&1 | perl -lane 'print $1 if /(\\d{4})x\\d{4}/'"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
    return process.communicate()[0].decode("utf-8", "ignore").strip("\n")

def getVideoQuality(videoWidth):
    if int(getVideoWidth(videoWidth)) < 3000:
        return "30"
    else:
        return "35"

def filenamesInDir(dir):
    filenames = [f for f in os.listdir(dir) if not f.startswith(".") and os.path.isfile(os.path.join(dir, f))]
    filenames.sort()
    return filenames

def getHighestResolutionVideoStreamIndex(path):
    command = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v',
        '-show_entries', 'stream=index,width,height',
        '-of', 'json',
        path
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        streams = data.get('streams', [])
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return 0

    if len(streams) == 0:
        return 0

    bestStream = max(
        streams,
        key=lambda s: (
            int(s.get('width') or 0) * int(s.get('height') or 0),
            int(s.get('width') or 0),
            int(s.get('height') or 0)
        )
    )
    return int(bestStream.get('index', 0))

def getNormalizedDualCameraDatetime(filename):
    # Expected format: YYYY_MMDD_HHMMSS_a.MP4 or YYYY_MMDD_HHMMSS_b.MP4
    components = filename.split("_")
    return datetime.datetime(int(components[0]),
                            int(components[1][:2]),
                            int(components[1][-2:]),
                            int(components[2][:2]),
                            int(components[2][2:4]),
                            int(components[2][-2:]))

def compressDualCameraVideos(outputDir, completedDir, processor, codec, quality):
    filenames = list(filter(lambda f: f.endswith("_a.MP4") or f.endswith("_b.MP4"), filenamesInDir(outputDir)))
    if len(filenames) == 0:
        logging.warning("Didn't find any _a/_b file to process: " + outputDir)
        return

    # Input #0 is always the _b camera in paired mode, so apply hflip here for all models.
    overlayFilter = '[0]crop=iw:ih*3/4:0:ih/8[overlay];[overlay]hflip[overlay];[overlay]format=yuva420p,geq=lum=\'p(X,Y)\':a=\'if(gt(abs(W/2-X),W/2-32)*gt(abs(H/2-Y),H/2-32),if(lte(hypot(32-(W/2-abs(W/2-X)),32-(H/2-abs(H/2-Y))),32),255,0),255)\'[overlay];[overlay][1]scale2ref=iw/3:ow/mdar[overlay][main];[main][overlay]overlay=main_w/3:main_h/50'

    skipNextFile = False
    for i in range(len(filenames)):
        if skipNextFile:
            skipNextFile = False
            continue
        filenameCurr = filenames[i]
        filenameNext = filenames[i] if (i == len(filenames) - 1) else filenames[i + 1]
        dtCurr = getNormalizedDualCameraDatetime(filenameCurr)
        dtNext = getNormalizedDualCameraDatetime(filenameNext)
        interval = abs((dtCurr - dtNext).total_seconds())

        # If both A & B are found (10 seconds tolerance), compress them to the same PIP video
        if filenameCurr != filenameNext and interval <= 10:
            mainFile = os.path.join(outputDir, (filenameCurr if filenameCurr.endswith("_a.MP4") else filenameNext))
            outputPath = mainFile[:-6]
            overlayFile = os.path.join(outputDir, (filenameNext if filenameNext.endswith("_b.MP4") else filenameCurr))
            command = ['ffmpeg', '-stats', '-loglevel', 'error', '-hwaccel', 'auto',
                        '-i', overlayFile,
                        '-i', mainFile,
                        '-filter_complex', overlayFilter,
                        '-c:a', 'aac',
                        '-b:a', '64k',
                        '-ac', '1']
            if codec == 0: # HEVC
                command.extend(['-vtag', 'hvc1'])
                if processor == 0: # CPU
                    command.extend([
                        '-c:v', 'libx265',
                        '-preset', '5',
                        '-x265-params', 'log-level=error',
                        '-g', '240',
                        '-b:v', '0',
                        '-crf', str(quality if quality != 0 else getVideoQuality(mainFile))
                        ])
                elif processor == 1: # Nvidia GPU
                    command.extend([
                        '-c:v', 'hevc_nvenc',
                        '-rc', 'constqp',
                        '-qp', str(quality if quality != 0 else 37)
                        ])
                elif processor == 2: # Apple GPU
                    command.extend([
                        '-c:v', 'hevc_videotoolbox',
                        '-q:v', str(quality if quality != 0 else 25),
                        '-g', '240'
                        ])
                outputPath = outputPath + ".mp4"
                command.append(outputPath)
            elif codec == 1: # AV1
                command.extend(['-c:v', 'libaom-av1',
                                '-cpu-used', '8',
                                '-row-mt', '1',
                                '-tiles', '2x2',
                                '-preset', '8',
                                '-svtav1-params', 'fast-decode=1',
                                '-crf', str(quality if quality != 0 else 55),
                                '-b:v', '0'
                                ])
                outputPath = outputPath + "_AV1.mp4"
                command.append(outputPath)
            logging.info("Compressing PIP video \t" + outputPath)
            process = subprocess.Popen(command, stdout=subprocess.PIPE)
            process.wait()
            shutil.move(mainFile, completedDir)
            shutil.move(overlayFile, completedDir)
            skipNextFile = True
        # If only A or B is found, and file still exists, compress it only
        elif filenameCurr.endswith("_a.MP4") or filenameCurr.endswith("_b.MP4"):
            filePath = os.path.join(outputDir, filenameCurr)
            outputPath = filePath[:-6]
            command = ['ffmpeg', '-stats', '-loglevel', 'error', '-hwaccel', 'auto',
                        '-i', filePath,
                        '-c:a', 'aac',
                        '-b:a', '64k',
                        '-ac', '1']
            if codec == 0: # HEVC
                command.extend(['-vtag', 'hvc1'])
                if processor == 0:
                    command.extend([
                        '-c:v', 'libx265',
                        '-preset', '5',
                        '-x265-params', 'log-level=error',
                        '-g', '240',
                        '-b:v', '0',
                        '-crf', str(quality if quality != 0 else getVideoQuality(filePath))
                        ])
                elif processor == 1:
                    command.extend([
                        '-c:v', 'hevc_nvenc',
                        '-rc', 'constqp',
                        '-qp', str(quality if quality != 0 else 37)
                        ])
                elif processor == 2:
                    command.extend([
                        '-c:v', 'hevc_videotoolbox',
                        '-q:v', str(quality if quality != 0 else 25),
                        '-g', '240'
                        ])
                outputPath = outputPath + ".mp4"
                command.append(outputPath)
            else:
                command.extend(['-c:v', 'libaom-av1',
                                '-cpu-used', '8',
                                '-row-mt', '1',
                                '-tiles', '2x2',
                                '-preset', '8',
                                '-svtav1-params', 'fast-decode=1',
                                '-crf', str(quality if quality != 0 else 55),
                                '-b:v', '0'
                                ])
                outputPath = outputPath + "_AV1.mp4"
                command.append(outputPath)
            logging.info("Compressing video \t" + outputPath)
            process = subprocess.Popen(command, stdout=subprocess.PIPE)
            process.wait()
            shutil.move(filePath, completedDir)

def compressVideos(outputDir, processor, codec, quality, model):
    completedDir = os.path.join(outputDir, 'completed')
    if not os.path.exists(completedDir):
        os.makedirs(completedDir)
    if model == "d5":
        compressDualCameraVideos(outputDir, completedDir, processor, codec, quality)
    elif model == "fitcamx":
        compressDualCameraVideos(outputDir, completedDir, processor, codec, quality)
    elif  model == "s80wifi":
        filenames = list(filter(lambda f: f.endswith("A.MP4") or f.endswith("B.MP4"), filenamesInDir(outputDir)))
        if len(filenames) == 0:
            logging.warning("Didn't find any file to process for PAPAGO S80Wifi: " + outputDir)
            return
        skipNextFile = False
        for i in range(len(filenames)):
            if skipNextFile:
                skipNextFile = False
                continue
            # Look for related front(A)/back(B) videos
            filenameCurr = filenames[i]
            filenameNext = filenames[i] if (i == len(filenames) - 1) else filenames[i + 1]
            dtCurr = getDatetime(filenameCurr, model)
            dtNext = getDatetime(filenameNext, model)
            interval = abs((dtCurr - dtNext).total_seconds())
            # If both A & B are found (10 seconds tolerance), compress them to the same PIP video
            if filenameCurr != filenameNext and interval <= 10:
                mainFile = os.path.join(outputDir, (filenameCurr if filenameCurr.endswith("A.MP4") else filenameNext))
                overlayFile = os.path.join(outputDir, (filenameNext if filenameNext.endswith("B.MP4") else filenameCurr))
                outputPath = mainFile[:-5] + ".mp4"
                if processor == 0: # CPU
                    command = "ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]crop=iw:ih*3/4:0:ih/8[overlay];[overlay]hflip[overlay];[overlay]format=yuva420p,geq=lum='p(X,Y)':a='if(gt(abs(W/2-X),W/2-32)*gt(abs(H/2-Y),H/2-32),if(lte(hypot(32-(W/2-abs(W/2-X)),32-(H/2-abs(H/2-Y))),32),255,0),255)'[overlay];[overlay][1]scale2ref=iw/3:ow/mdar[overlay][main];[main][overlay]overlay=main_w/3:main_h/50\" -c:v libx265 -preset 5 -vtag hvc1 -x265-params log-level=error -crf " + str(quality if quality != 0 else getVideoQuality(mainFile)) + " -c:a aac -b:a 64k -ac 1 " + outputPath
                elif processor == 1: # Nvidia GPU
                    command = "ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]crop=iw:ih*3/4:0:ih/8[overlay];[overlay]hflip[overlay];[overlay]format=yuva420p,geq=lum='p(X,Y)':a='if(gt(abs(W/2-X),W/2-32)*gt(abs(H/2-Y),H/2-32),if(lte(hypot(32-(W/2-abs(W/2-X)),32-(H/2-abs(H/2-Y))),32),255,0),255)'[overlay];[overlay][1]scale2ref=iw/3:ow/mdar[overlay][main];[main][overlay]overlay=main_w/3:main_h/50\" -c:v hevc_nvenc -vtag hvc1 -rc constqp -qp " + str(quality if quality != 0 else 37) + " -c:a aac -b:a 64k -ac 1 " + outputPath 
                elif processor == 2: # Apple GPU
                    command = "ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]crop=iw:ih*3/4:0:ih/8[overlay];[overlay]hflip[overlay];[overlay]format=yuva420p,geq=lum='p(X,Y)':a='if(gt(abs(W/2-X),W/2-32)*gt(abs(H/2-Y),H/2-32),if(lte(hypot(32-(W/2-abs(W/2-X)),32-(H/2-abs(H/2-Y))),32),255,0),255)'[overlay];[overlay][1]scale2ref=iw/3:ow/mdar[overlay][main];[main][overlay]overlay=main_w/3:main_h/50\" -c:v hevc_videotoolbox -q:v " + str(quality if quality != 0 else 25) + " -g 240 -vtag hvc1 -c:a aac -b:a 64k -ac 1 " + outputPath 
                logging.info("Compressing PIP video \t" + outputPath)
                process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
                process.wait()
                shutil.move(mainFile, completedDir)
                shutil.move(overlayFile, completedDir)
                skipNextFile = True
            # If only A or B is found, and file still exists, compress it only
            elif filenameCurr.endswith("A.MP4") or filenameCurr.endswith("B.MP4"):
                filePath = os.path.join(outputDir, filenameCurr)
                outputPath = filePath[:-5] + ".mp4"
                if processor == 0: # CPU
                    command = "ffmpeg -stats -loglevel error -i " + filePath + " -c:v libx265 -preset 5 -vtag hvc1 -x265-params log-level=error -crf " + str(quality if quality != 0 else getVideoQuality(filePath)) + " -c:a aac -b:a 64k -ac 1 " + outputPath
                elif processor == 1: # Nvidia GPU
                    command = "ffmpeg -stats -loglevel error -i " + filePath + " -c:v hevc_nvenc -vtag hvc1 -rc constqp -qp " + str(quality if quality != 0 else 37) + " -c:a aac -b:a 64k -ac 1 " + outputPath 
                elif processor == 2: # Apple GPU
                    command = "ffmpeg -stats -loglevel error -i " + filePath + " -c:v hevc_videotoolbox -q:v " + str(quality if quality != 0 else 25) + " -g 240 -vtag hvc1 -c:a aac -b:a 64k -ac 1 " + outputPath 
                logging.info("Compressing video \t" + outputPath)
                process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
                process.wait()
                shutil.move(filePath, completedDir)
    elif model == "s36":
        filenames = list(filter(lambda f: f.endswith(".MOV"), filenamesInDir(outputDir)))
        if len(filenames) == 0:
            logging.warning("Didn't find any file to process for PAPAGO S36: " + outputDir)
            return
        for i in range(len(filenames)):
            filePath = os.path.join(outputDir, filenames[i])
            if filePath.endswith(".MOV"):
                outputPath = filePath[:-4] + ".mp4"
                if processor == 0: # CPU
                    command = "ffmpeg -stats -loglevel error -i " + filePath + " -c:v libx265 -preset 5 -vtag hvc1 -x265-params log-level=error -crf " + str(quality if quality != 0 else getVideoQuality(filePath)) + " -c:a aac -b:a 64k -ac 1 " + outputPath
                elif processor == 1: # Nvidia GPU
                    command = "ffmpeg -stats -loglevel error -i " + filePath + " -c:v hevc_nvenc -vtag hvc1 -rc constqp -qp " + str(quality if quality != 0 else 37) + " -c:a aac -b:a 64k -ac 1 " + outputPath 
                elif processor == 2: # Apple GPU
                    command = "ffmpeg -stats -loglevel error -i " + filePath + " -c:v hevc_videotoolbox -q:v " + str(quality if quality != 0 else 25) + " -g 240 -vtag hvc1 -c:a aac -b:a 64k -ac 1 " + outputPath 
                logging.info("Compressing video \t" + outputPath)
                process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
                process.wait()
                shutil.move(filePath, completedDir)

def catAndCopyFiles(filenames, inputDir, outputDir, model):
    # Create directory if not exists
    if not os.path.exists(outputDir):
        os.makedirs(outputDir)
    # Create a temp file in the output directory
    logging.info("Copy video clips:\n" + ("\n".join(filenames)))
    filename = filenames[0]
    outputFilename = filename
    if model == "d5":
        timestamp = getD5OutputPrefix(filename)
        camera = filename[-5].lower()
        outputFilename = timestamp + "_" + camera + ".MP4"
    if model == "fitcamx":
        timestamp = getFitcamxOutputPrefix(filename)
        camera = filename[-4]
        outputFilename = timestamp + "_" + camera.lower() + ".MP4"
    # Temp file path
    output = os.path.join(outputDir, outputFilename)
    # Check if we can skip
    if os.path.exists(output):
        logging.info("Temp file already exists, skip video clip \"" + output + "\"")
        return False
    if model == "d5":
        allCompressedFileNames = list(filter(lambda f: not f.endswith("_a.MP4") and not f.endswith("_b.MP4"), filenamesInDir(outputDir)))
        outputPrefix = getD5OutputPrefix(filename)
        if len(list(filter(lambda f: f.startswith(outputPrefix), allCompressedFileNames))) > 0:
            logging.info("Compressed file already exists, skip video clip \"" + output + "\"")
            return False
    elif model == "fitcamx":
        allCompressedFileNames = list(filter(lambda f: not f.endswith("_a.MP4") and not f.endswith("_b.MP4"), filenamesInDir(outputDir)))
        outputPrefix = getFitcamxOutputPrefix(filename)
        if len(list(filter(lambda f: f.startswith(outputPrefix), allCompressedFileNames))) > 0:
            logging.info("Compressed file already exists, skip video clip \"" + output + "\"")
            return False
    elif  model == "s80wifi":
        allCompressedFileNames = list(filter(lambda f: not f.endswith("A.MP4") and not f.endswith("B.MP4"), filenamesInDir(outputDir)))
        if len(list(filter(lambda f: f.startswith(filename[:-10]), allCompressedFileNames))) > 0:
            logging.info("Compressed file already exists, skip video clip \"" + output + "\"")
            return False
    elif model == "s36":
        allCompressedFileNames = list(filter(lambda f: not f.endswith(".MOV"), filenamesInDir(outputDir)))
        if len(list(filter(lambda f: f.startswith(filename[:-4]), allCompressedFileNames))) > 0:
            logging.info("Compressed file already exists, skip video clip \"" + output + "\"")
            return False
    # Skip if temp file exists
    if os.path.exists(output):
        logging.info("Temp file already exists, skip video clip \"" + output + "\"")
        return True
    # If there is only 1 file, return the original path directly
    if len(filenames) == 1:
        inputPath= os.path.join(inputDir, filename)
        logging.info("-> \"" + output + "\"")
        if model == "fitcamx":
            command = ['ffmpeg', '-y', '-stats', '-loglevel', 'error', '-fflags', '+genpts', '-i', inputPath,
                       '-map', '0', '-c', 'copy', '-movflags', '+faststart', '-brand', 'mp42']
            if output.endswith("_a.MP4"):
                command.extend(['-tag:v', 'hvc1'])
            command.append(output)
            process = subprocess.Popen(command, stdout=subprocess.PIPE)
            process.wait()
        elif model == "d5":
            videoStreamIndex = getHighestResolutionVideoStreamIndex(inputPath)
            command = ['ffmpeg', '-y', '-stats', '-loglevel', 'error', '-i', inputPath,
                       '-map', '0:v:' + str(videoStreamIndex), '-map', '0:a:0?',
                       '-c', 'copy', '-movflags', '+faststart', '-tag:v', 'hvc1', output]
            process = subprocess.Popen(command, stdout=subprocess.PIPE)
            process.wait()
        else:
            shutil.copy(inputPath, output)
        return True
    # If there are multiple files, join all of them
    logging.info("-> \"" + output + "\"")
    inputPaths = list(map(lambda file: os.path.join(inputDir, file), filenames))
    # logging.info("Join Files:\n" + "\n".join(inputPaths))
    # generate "list.txt" file
    with open("list.txt", "w") as f:
        f.write("\n".join(map(lambda f: "file '" + f + "'", inputPaths)))
    if model == "fitcamx":
        command = ['ffmpeg', '-y', '-stats', '-loglevel', 'error', '-fflags', '+genpts',
                    '-err_detect', 'ignore_err', '-f', 'concat', '-safe', '0', '-i', 'list.txt',
                    '-map', '0', '-c', 'copy', '-movflags', '+faststart', '-brand', 'mp42']
        if output.endswith("_a.MP4"):
            command.extend(['-tag:v', 'hvc1'])
        command.append(output)
        process = subprocess.Popen(command, stdout=subprocess.PIPE)
        process.wait()
        return process.returncode == 0
    elif model == "d5":
        videoStreamIndex = getHighestResolutionVideoStreamIndex(inputPaths[0])
        command = ['ffmpeg', '-y', '-stats', '-loglevel', 'error', '-err_detect', 'ignore_err',
                    '-f', 'concat', '-safe', '0', '-i', 'list.txt',
                    '-map', '0:v:' + str(videoStreamIndex), '-map', '0:a:0?',
                    '-c', 'copy', '-movflags', '+faststart', '-tag:v', 'hvc1', output]
        process = subprocess.Popen(command, stdout=subprocess.PIPE)
        process.wait()
        return process.returncode == 0
    else:
        command = "ffmpeg -stats -loglevel error -err_detect ignore_err -f concat -safe 0 -i list.txt -c copy " + output
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
        process.wait()
        return process.returncode == 0

# Try to detect relationships and link files
# If files are related (based on the clip length), they will be linked together
# Else, simply copy to the output directory
def catFiles(filenames, inputDir, outputDir, clipLength, model):
    files = []
    for i in range(len(filenames)):
        fileCurr = filenames[i]
        # If it's the 1st file, simply add to list
        if i == 0:
            files.append(fileCurr) 
        else:
            dtPrev = getDatetime(filenames[i-1], model)
            dtCurr = getDatetime(fileCurr, model)
            interval = (dtCurr - dtPrev).total_seconds()
            # If it's linked to the last file, add to list
            if abs(interval) <= (clipLength + 30): # 30 seconds tolerance
                files.append(fileCurr)
            # Else, join the current files list
            else:
                catAndCopyFiles(files, inputDir, outputDir, model)
                # And start a new list
                files = [fileCurr]
        # If it's the last file, join the files in the list
        if i == len(filenames) - 1:
            catAndCopyFiles(files, inputDir, outputDir, model)

def process(inputDir, outputDir, clipLength, processor, codec, quality, model):
    if os.path.exists(inputDir):
        filenames = filenamesInDir(inputDir)
        if model == "d5":
            filenamesA, filenamesB = [], []
            for filename in filenames:
                if filename.endswith("a.MP4"):
                    filenamesA.append(filename)
                elif filename.endswith("b.MP4"):
                    filenamesB.append(filename)
            catFiles(filenamesA, inputDir, outputDir, clipLength, model)
            catFiles(filenamesB, inputDir, outputDir, clipLength, model)
            compressVideos(outputDir, processor, codec, quality, model)
        elif  model == "s80wifi":
            filenamesA, filenamesB = [], []
            for filename in filenames:
                if filename.endswith("A.MP4"):
                    filenamesA.append(filename)
                elif filename.endswith("B.MP4"):
                    filenamesB.append(filename)
            catFiles(filenamesA, inputDir, outputDir, clipLength, model)
            catFiles(filenamesB, inputDir, outputDir, clipLength, model)
            compressVideos(outputDir, processor, codec, quality, model)
        elif model == "s36":
            catFiles(filenames, inputDir, outputDir, clipLength, model)
            compressVideos(outputDir, processor, codec, quality, model)
        elif model == "fitcamx":
            cardvDir = inputDir
            moveFitcamxEmrToMovie(cardvDir)
            frontDir = os.path.join(cardvDir, "Movie")
            rearDir = os.path.join(cardvDir, "Movie_E")
            filenamesA = list(filter(lambda f: f.endswith("A.TS"), filenamesInDir(frontDir))) if os.path.isdir(frontDir) else []
            filenamesB = list(filter(lambda f: f.endswith("B.TS"), filenamesInDir(rearDir))) if os.path.isdir(rearDir) else []
            catFiles(filenamesA, frontDir, outputDir, clipLength, model)
            catFiles(filenamesB, rearDir, outputDir, clipLength, model)
            compressVideos(outputDir, processor, codec, quality, model)
    else:
        if model == "d5":
            compressVideos(outputDir, processor, codec, quality, model)
        elif  model == "s80wifi":
            compressVideos(outputDir, processor, codec, quality, model)
        elif model == "s36":
            compressVideos(outputDir, processor, codec, quality, model)
        elif model == "fitcamx":
            compressVideos(outputDir, processor, codec, quality, model)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", dest = "input", help = "Input Directory", type = str)
    parser.add_argument("-o", "--output", dest = "output", help = "Output Directory", type = str)
    parser.add_argument("-l", "--length", dest = "length", help = "Clip Length in second", type = int, default = 300)
    parser.add_argument("-p", "--processor", dest = "processor", help = "Process Type, 0 = CPU, 1 = Nvidia GPU, 2 = Apple GPU", type = int, default = 0)
    parser.add_argument("-c", "--codec", dest = "codec", help = "Codec, 0 = HEVC, 1 = AV1", type = int, default = 0)
    parser.add_argument("-q", "--quality", dest = "quality", help = "Quality (CRF/CQ)", type = int, default = 0)
    parser.add_argument("-m", "--model", dest = "model", help = "Dash cam model (d5, s80wifi, s36, fitcamx)", type = str, default="d5")
    args = parser.parse_args()
    if args.processor != 0 and args.processor != 1 and args.processor != 2:
        logging.error("Unknown processor parameter")
    else:
        process(args.input, args.output, args.length, args.processor, args.codec, args.quality, args.model)
