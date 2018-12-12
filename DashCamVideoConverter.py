import argparse
import datetime
import os
import subprocess
import tempfile

def getDatetime(dtStr):
    components = dtStr.split("_") # Date time conponents
    return datetime.datetime(int(components[0]), # Year
                             int(components[1][:2]), # Month
                             int(components[1][-2:]), # Day
                             int(components[2][:2]), # Hour
                             int(components[2][2:4]), # Minute
                             int(components[2][-2:])) # Second

def filenamesInDir(dir):
    filenames = [f for f in os.listdir(dir) if not f.startswith(".") and os.path.isfile(os.path.join(dir, f))]
    filenames.sort()
    return filenames

def makePIPVideos(outputDir, isCPUMode):
    filenames = filenamesInDir(outputDir)
    if len(filenames) == 0:
        return
    # Find related main/overlay videos
    # main video name always ends with A
    # overlay video name always ends with B
    for i in range(len(filenames)):
        if i == len(filenames) - 1: # Last file
            break
        filenameCurr = filenames[i]
        filenameNext = filenames[i+1]
        dtCurr = getDatetime(filenameCurr)
        dtNext = getDatetime(filenameNext)
        interval = abs((dtCurr - dtNext).total_seconds())
        if interval < 2:
            mainFile = os.path.join(outputDir, (filenameCurr if filenameCurr.endswith("A.MP4") else filenameNext))
            overlayFile = os.path.join(outputDir, (filenameNext if filenameNext.endswith("B.MP4") else filenameCurr))
            outputPath = mainFile[:-5] + ".mp4"
            if isCPUMode:
                command = "ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]scale=iw/3:ih/3,crop=iw:ih*3/4:0:ih/8[pip];[1][pip] overlay=main_w/3:0\" -c:v libx265 -x265-params log-level=error -crf 37 -c:a aac -b:a 64k -ac 1 " + outputPath
            else:
                command = "ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]scale=iw/3:ih/3,crop=iw:ih*3/4:0:ih/8[pip];[1][pip] overlay=main_w/3:0\" -c:v hevc_nvenc -rc constqp -qp 37 -c:a aac -b:a 64k -ac 1 " + outputPath 
            print("Making PIP \t" + outputPath)
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
            process.wait()
            if os.path.exists(outputPath) and os.path.getsize(outputPath) > 0:
                print("Deleting \t" + mainFile)
                os.remove(mainFile)
                print("Deleting \t" + overlayFile)
                os.remove(overlayFile)

def joinSequentialFiles(filenames, inputDir, outputDir):
    filename = filenames[0]
    # Check if we can skip
    output = os.path.join(outputDir, filename)
    if os.path.exists(output):
        print("Converted file already exists, skip joining & compressing for " + output)
        return None, None, False
    allPIPFileNames = list(filter(lambda f: not f.endswith("A.MP4") and not f.endswith("B.MP4"), filenamesInDir(outputDir)))
    if len(list(filter(lambda f: f.startswith(filename[:-10]), allPIPFileNames))) > 0:
        print("PIP file already exists, skip joining & compressing for " + output)
        return None, None, False
    # Create directory if not exists
    if not os.path.exists(outputDir):
        os.makedirs(outputDir)
    # Prepare temp output path
    output = os.path.join(outputDir, filename)
    # Skip if temp file exists
    if os.path.exists(output):
        print("Concatenated file already exists, skip joining for " + output)
        return output, outputDir, True
    # If there is only 1 file, return the original path directly
    if len(filenames) == 1:
        return os.path.join(inputDir, filename), outputDir, False
    # If there are multiple files, join all of them
    print("Copying files to " + output)
    inputPaths = list(map(lambda file: os.path.join(inputDir, file), filenames))
    # print("Join Files:\n" + "\n".join(inputPaths))
    # generate "list.txt" file
    with open("list.txt", "w") as f:
        f.write("\n".join(map(lambda f: "file '" + f + "'", inputPaths)))
    command = "ffmpeg -stats -loglevel error -err_detect ignore_err -f concat -safe 0 -i list.txt -c copy " + output
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
    process.wait()
    return output, outputDir, True

def joinFiles(filenames, inputDir, outputDir, clipDuration):
    linkedFiles = []
    for i in range(len(filenames)):
        fileCurr = filenames[i]
        if i == 0:
            linkedFiles.append(fileCurr) # First file, simply add to list
        else:
            dtPrev = getDatetime(filenames[i-1])
            dtCurr = getDatetime(fileCurr)
            interval = (dtCurr - dtPrev).total_seconds()
            if abs(interval - clipDuration) <= 3:
                linkedFiles.append(fileCurr) # Linked file, add to list
            else:
                joinSequentialFiles(linkedFiles, inputDir, outputDir) # Unlinked file, join the files in the current list
                linkedFiles = [fileCurr] # Start a new list
        if i == len(filenames) - 1:
            joinSequentialFiles(linkedFiles, inputDir, outputDir) # Last file, join the files in the list

def process(inputDir, outputDir, clipDuration, isCPUMode):
    filenames = filenamesInDir(inputDir)
    if len(filenames) == 0:
        return
    listA, listB = [], []
    for filename in filenames:
        if filename.endswith("A.MP4"):
            listA.append(filename)
        else:
            listB.append(filename)
    joinFiles(listA, inputDir, outputDir, clipDuration)
    joinFiles(listB, inputDir, outputDir, clipDuration)
    makePIPVideos(outputDir, isCPUMode)

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", dest = "input", help = "Input Directory", type = str)
    parser.add_argument("-o", "--output", dest = "output", help = "Output Directory", type = str)
    parser.add_argument("-c", "--cpu", dest = "cpu", default = True, help = "CPU Mode", type = bool)
    parser.add_argument("-d", "--duration", dest = "duration", default = 300, help = "Clip Duration", type = int)
    args = parser.parse_args()

    process(args.input, args.output, args.duration, args.cpu)
