import argparse
import datetime
import os
import shutil
import subprocess
import tempfile

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

def compressVideos(outputDir, processor, model):
    completedDir = os.path.join(outputDir, 'completed')
    if not os.path.exists(completedDir):
        os.makedirs(completedDir)
    if model == "d5":
        filenames = list(filter(lambda f: f.endswith("a.MP4") or f.endswith("b.MP4"), filenamesInDir(outputDir)))
        if len(filenames) == 0:
            print("Didn't find any file to process for PAPAGO D5: " + outputDir)
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
                mainFile = os.path.join(outputDir, (filenameCurr if filenameCurr.endswith("a.MP4") else filenameNext))
                overlayFile = os.path.join(outputDir, (filenameNext if filenameNext.endswith("b.MP4") else filenameCurr))
                outputPath = mainFile[:-9] + ".mp4"
                if processor == 0: # CPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]crop=iw:ih*3/4:0:ih/8[overlay];[overlay]format=yuva420p,geq=lum='p(X,Y)':a='if(gt(abs(W/2-X),W/2-32)*gt(abs(H/2-Y),H/2-32),if(lte(hypot(32-(W/2-abs(W/2-X)),32-(H/2-abs(H/2-Y))),32),255,0),255)'[overlay];[overlay][1]scale2ref=iw/3:ow/mdar[overlay][main];[main][overlay]overlay=main_w/3:main_h/50\" -c:v libx265 -preset 5 -vtag hvc1 -x265-params log-level=error -crf " + getVideoQuality(mainFile) + " -c:a aac -b:a 64k -ac 1 " + outputPath
                elif processor == 1: # Nvidia GPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]crop=iw:ih*3/4:0:ih/8[overlay];[overlay]format=yuva420p,geq=lum='p(X,Y)':a='if(gt(abs(W/2-X),W/2-32)*gt(abs(H/2-Y),H/2-32),if(lte(hypot(32-(W/2-abs(W/2-X)),32-(H/2-abs(H/2-Y))),32),255,0),255)'[overlay];[overlay][1]scale2ref=iw/3:ow/mdar[overlay][main];[main][overlay]overlay=main_w/3:main_h/50\" -c:v hevc_nvenc -vtag hvc1 -rc constqp -qp 37 -c:a aac -b:a 64k -ac 1 " + outputPath 
                elif processor == 2: # Apple GPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]crop=iw:ih*3/4:0:ih/8[overlay];[overlay]format=yuva420p,geq=lum='p(X,Y)':a='if(gt(abs(W/2-X),W/2-32)*gt(abs(H/2-Y),H/2-32),if(lte(hypot(32-(W/2-abs(W/2-X)),32-(H/2-abs(H/2-Y))),32),255,0),255)'[overlay];[overlay][1]scale2ref=iw/3:ow/mdar[overlay][main];[main][overlay]overlay=main_w/3:main_h/50\" -c:v hevc_videotoolbox -vtag hvc1 -c:a aac -b:a 64k -ac 1 " + outputPath 
                print("Compressing PIP video \t" + outputPath)
                process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
                process.wait()
                shutil.move(mainFile, completedDir)
                shutil.move(overlayFile, completedDir)
                skipNextFile = True
            # If only A or B is found, and file still exists, compress it only
            elif filenameCurr.endswith("a.MP4") or filenameCurr.endswith("b.MP4"):
                filePath = os.path.join(outputDir, filenameCurr)
                outputPath = filePath[:-9] + ".mp4"
                if processor == 0: # CPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + filePath + " -c:v libx265 -preset 5 -vtag hvc1 -x265-params log-level=error -crf " + getVideoQuality(filePath) + " -c:a aac -b:a 64k -ac 1 " + outputPath
                elif processor == 1: # Nvidia GPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + filePath + " -c:v hevc_nvenc -vtag hvc1 -rc constqp -qp 37 -c:a aac -b:a 64k -ac 1 " + outputPath 
                elif processor == 2: # Apple GPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + filePath + " -c:v hevc_videotoolbox -vtag hvc1 -c:a aac -b:a 64k -ac 1 " + outputPath 
                print("Compressing video \t" + outputPath)
                process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
                process.wait()
                shutil.move(filePath, completedDir)
    elif  model == "s80wifi":
        filenames = list(filter(lambda f: f.endswith("A.MP4") or f.endswith("B.MP4"), filenamesInDir(outputDir)))
        if len(filenames) == 0:
            print("Didn't find any file to process for PAPAGO S80Wifi: " + outputDir)
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
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]crop=iw:ih*3/4:0:ih/8[overlay];[overlay]format=yuva420p,geq=lum='p(X,Y)':a='if(gt(abs(W/2-X),W/2-32)*gt(abs(H/2-Y),H/2-32),if(lte(hypot(32-(W/2-abs(W/2-X)),32-(H/2-abs(H/2-Y))),32),255,0),255)'[overlay];[overlay][1]scale2ref=iw/3:ow/mdar[overlay][main];[main][overlay]overlay=main_w/3:main_h/50\" -c:v libx265 -preset 5 -vtag hvc1 -x265-params log-level=error -crf " + getVideoQuality(mainFile) + " -c:a aac -b:a 64k -ac 1 " + outputPath
                elif processor == 1: # Nvidia GPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]crop=iw:ih*3/4:0:ih/8[overlay];[overlay]format=yuva420p,geq=lum='p(X,Y)':a='if(gt(abs(W/2-X),W/2-32)*gt(abs(H/2-Y),H/2-32),if(lte(hypot(32-(W/2-abs(W/2-X)),32-(H/2-abs(H/2-Y))),32),255,0),255)'[overlay];[overlay][1]scale2ref=iw/3:ow/mdar[overlay][main];[main][overlay]overlay=main_w/3:main_h/50\" -c:v hevc_nvenc -vtag hvc1 -rc constqp -qp 37 -c:a aac -b:a 64k -ac 1 " + outputPath 
                elif processor == 2: # Apple GPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]crop=iw:ih*3/4:0:ih/8[overlay];[overlay]format=yuva420p,geq=lum='p(X,Y)':a='if(gt(abs(W/2-X),W/2-32)*gt(abs(H/2-Y),H/2-32),if(lte(hypot(32-(W/2-abs(W/2-X)),32-(H/2-abs(H/2-Y))),32),255,0),255)'[overlay];[overlay][1]scale2ref=iw/3:ow/mdar[overlay][main];[main][overlay]overlay=main_w/3:main_h/50\" -c:v hevc_videotoolbox -vtag hvc1 -c:a aac -b:a 64k -ac 1 " + outputPath 
                print("Compressing PIP video \t" + outputPath)
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
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + filePath + " -c:v libx265 -preset 5 -vtag hvc1 -x265-params log-level=error -crf " + getVideoQuality(filePath) + " -c:a aac -b:a 64k -ac 1 " + outputPath
                elif processor == 1: # Nvidia GPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + filePath + " -c:v hevc_nvenc -vtag hvc1 -rc constqp -qp 37 -c:a aac -b:a 64k -ac 1 " + outputPath 
                elif processor == 2: # Apple GPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + filePath + " -c:v hevc_videotoolbox -vtag hvc1 -c:a aac -b:a 64k -ac 1 " + outputPath 
                print("Compressing video \t" + outputPath)
                process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
                process.wait()
                shutil.move(filePath, completedDir)
    elif model == "s36":
        filenames = list(filter(lambda f: f.endswith(".MOV"), filenamesInDir(outputDir)))
        if len(filenames) == 0:
            print("Didn't find any file to process for PAPAGO S36: " + outputDir)
            return
        for i in range(len(filenames)):
            filePath = os.path.join(outputDir, filenames[i])
            if filePath.endswith(".MOV"):
                outputPath = filePath[:-4] + ".mp4"
                if processor == 0: # CPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + filePath + " -c:v libx265 -preset 5 -vtag hvc1 -x265-params log-level=error -crf " + getVideoQuality(filePath) + " -c:a aac -b:a 64k -ac 1 " + outputPath
                elif processor == 1: # Nvidia GPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + filePath + " -c:v hevc_nvenc -vtag hvc1 -rc constqp -qp 37 -c:a aac -b:a 64k -ac 1 " + outputPath 
                elif processor == 2: # Apple GPU
                    command = "/usr/local/bin/ffmpeg -stats -loglevel error -i " + filePath + " -c:v hevc_videotoolbox -vtag hvc1 -c:a aac -b:a 64k -ac 1 " + outputPath 
                print("Compressing video \t" + outputPath)
                process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
                process.wait()
                shutil.move(filePath, completedDir)

def catAndCopyFiles(filenames, inputDir, outputDir, model):
    # Create directory if not exists
    if not os.path.exists(outputDir):
        os.makedirs(outputDir)
    # Create a temp file in the output directory
    print("Cat & copy files:\n" + ("\n".join(filenames)))
    filename = filenames[0]
    # Temp file path
    output = os.path.join(outputDir, filename)
    # Check if we can skip
    if os.path.exists(output):
        print("Temp file already exists, skip cat & copy for \"" + output + "\"")
        return False
    if model == "d5":
        allCompressedFileNames = list(filter(lambda f: not f.endswith("a.MP4") and not f.endswith("b.MP4"), filenamesInDir(outputDir)))
        if len(list(filter(lambda f: f.startswith(filename[:-10]), allCompressedFileNames))) > 0:
            print("Compressed file already exists, skip cat & copy for \"" + output + "\"")
            return False
    elif  model == "s80wifi":
        allCompressedFileNames = list(filter(lambda f: not f.endswith("A.MP4") and not f.endswith("B.MP4"), filenamesInDir(outputDir)))
        if len(list(filter(lambda f: f.startswith(filename[:-10]), allCompressedFileNames))) > 0:
            print("Compressed file already exists, skip cat & copy for \"" + output + "\"")
            return False
    elif model == "s36":
        allCompressedFileNames = list(filter(lambda f: not f.endswith(".MOV"), filenamesInDir(outputDir)))
        if len(list(filter(lambda f: f.startswith(filename[:-4]), allCompressedFileNames))) > 0:
            print("Compressed file already exists, skip cat & copy for \"" + output + "\"")
            return False
    # Skip if temp file exists
    if os.path.exists(output):
        print("Temp file already exists, skip cat & copy for \"" + output + "\"")
        return True
    # If there is only 1 file, return the original path directly
    if len(filenames) == 1:
        inputPath= os.path.join(inputDir, filename)
        print("-> \"" + output + "\"")
        shutil.copy(inputPath, output)
        return True
    # If there are multiple files, join all of them
    print("-> \"" + output + "\"")
    inputPaths = list(map(lambda file: os.path.join(inputDir, file), filenames))
    # print("Join Files:\n" + "\n".join(inputPaths))
    # generate "list.txt" file
    with open("list.txt", "w") as f:
        f.write("\n".join(map(lambda f: "file '" + f + "'", inputPaths)))
    command = "ffmpeg -stats -loglevel error -err_detect ignore_err -f concat -safe 0 -i list.txt -c copy " + output
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
    process.wait()
    return True

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

def process(inputDir, outputDir, clipLength, processor, model):
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
            compressVideos(outputDir, processor, model)
        elif  model == "s80wifi":
            filenamesA, filenamesB = [], []
            for filename in filenames:
                if filename.endswith("A.MP4"):
                    filenamesA.append(filename)
                elif filename.endswith("B.MP4"):
                    filenamesB.append(filename)
            catFiles(filenamesA, inputDir, outputDir, clipLength, model)
            catFiles(filenamesB, inputDir, outputDir, clipLength, model)
            compressVideos(outputDir, processor, model)
        elif model == "s36":
            catFiles(filenames, inputDir, outputDir, clipLength, model)
            compressVideos(outputDir, processor, model)
    else:
        if model == "d5":
            compressVideos(outputDir, processor, model)
        elif  model == "s80wifi":
            compressVideos(outputDir, processor, model)
        elif model == "s36":
            compressVideos(outputDir, processor, model)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", dest = "input", help = "Input Directory", type = str)
    parser.add_argument("-o", "--output", dest = "output", help = "Output Directory", type = str)
    parser.add_argument("-l", "--length", dest = "length", help = "Clip Length in second", type = int, default = 300)
    parser.add_argument("-p", "--processor", dest = "processor", help = "Process Type, 0 = CPU, 1 = Nvidia GPU, 2 = Apple GPU", type = int, default = 0)
    parser.add_argument("-m", "--model", dest = "model", help = "Dash cam model (d5, s80wifi, s36)", type = str, default="d5")
    args = parser.parse_args()
    if args.processor != 0 and args.processor != 1 and args.processor != 2:
        print("Unknown processor parameter")
    else:
        process(args.input, args.output, args.length, args.processor, args.model)
