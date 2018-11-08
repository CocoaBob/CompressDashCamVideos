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

def joinFiles(filenames, inputDir, outputDir):
    # Check if we can skip
    output = os.path.join(outputDir, filenames[0])
    if os.path.exists(output):
        print("Converted file already exists, skip concatenating & compressing for " + output)
        return None
    # Create directory if not exists
    if not os.path.exists(outputDir):
        os.makedirs(outputDir)
    # Prepare temp output path
    tmpOutput = os.path.join(outputDir, "tmp."+filenames[0])
    # Skip if temp file exists
    if os.path.exists(tmpOutput):
        print("Concatenated file already exists, skip concatenating for " + tmpOutput)
        return tmpOutput
    # Start copying files to temp output
    print("Copying files to " + tmpOutput)
    # If there is only 1 file
    if len(filenames) == 1:
        command = "cp " + os.path.join(inputDir, filenames[0]) + " " + tmpOutput
        print(command)
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
        process.wait()
        return tmpOutput
    # If there are multiple files
    inputPaths = list(map(lambda file: os.path.join(inputDir, file), filenames))
    tempFile = tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', prefix='list')
    tempFile.write("\n".join(map(lambda f: "file '" + f + "'", inputPaths)))
    tempFile.flush()
    command = "ffmpeg -stats -loglevel panic -f concat -safe 0 -i " + tempFile.name + " -c copy " + tmpOutput
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
    process.wait()
    tempFile.close()
    return tmpOutput
    
def compressFile(path):
    if path is None:
        return
    intputPath = path
    outputPath = os.path.join(os.path.dirname(path), os.path.basename(path)[4:])
    command = "ffmpeg -stats -loglevel panic -hwaccel auto -i " + intputPath + " -c:v libx265 -x265-params log-level=error -crf 30 -c:a copy " + outputPath
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
    process.wait()
    os.remove(intputPath)

def processFiles(filenames, inputDir, outputDir, clipDuration):
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
                compressFile(joinFiles(linkedFiles, inputDir, outputDir)) # Unlinked file, link the list
                linkedFiles = [fileCurr] # Start a new list
        if i == len(filenames) - 1:
            compressFile(joinFiles(linkedFiles, inputDir, outputDir)) # Last file, link the list

def process(inputDir, outputDir, clipDuration):
    filenames = [f for f in os.listdir(inputDir) if not f.startswith(".") and os.path.isfile(os.path.join(inputDir, f))]
    if len(filenames) == 0:
        return
    filenames.sort()
    listA, listB = [], []
    for filename in filenames:
        if filename.endswith("A.MP4"):
            listA.append(filename)
        else:
            listB.append(filename)
    processFiles(listA, inputDir, outputDir, clipDuration)
    processFiles(listB, inputDir, outputDir, clipDuration)

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", dest = "input", help = "Input Directory", type = str)
    parser.add_argument("-o", "--output", dest = "output", help = "Output Directory", type = str)
    parser.add_argument("-d", "--duration", dest = "duration", default = 300, help = "Clip Duration", type = int)
    args = parser.parse_args()

    process(args.input, args.output, args.duration)
