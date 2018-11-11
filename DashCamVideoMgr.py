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
        return None, None, False
    # Create directory if not exists
    if not os.path.exists(outputDir):
        os.makedirs(outputDir)
    # Prepare temp output path
    tmpOutput = os.path.join(outputDir, "tmp."+filenames[0])
    # Skip if temp file exists
    if os.path.exists(tmpOutput):
        print("Concatenated file already exists, skip concatenating for " + tmpOutput)
        return tmpOutput, outputDir, True
    # If there is only 1 file, return the original path directly
    if len(filenames) == 1:
        return os.path.join(inputDir, filenames[0]), outputDir, False
    # If there are multiple files, join all of them
    print("Copying files to " + tmpOutput)
    inputPaths = list(map(lambda file: os.path.join(inputDir, file), filenames))
    # generate "list.txt" file
    with open("list.txt", "w") as f:
        f.write("\n".join(map(lambda f: "file '" + f + "'", inputPaths)))
    command = "ffmpeg -stats -loglevel error -f concat -safe 0 -i list.txt -c copy " + tmpOutput
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
    process.wait()
    return tmpOutput, outputDir, True
    
def compressFile((inputPath, outputDir, isTemp)):
    if inputPath is None:
        return
    filename = os.path.basename(inputPath)
    outputPath = os.path.join(outputDir, (filename[4:] if isTemp else filename))
    command = "ffmpeg -stats -loglevel error -i " + inputPath + " -c:v hevc_nvenc -rc constqp -qp 37 -r 20 -c:a aac -b:a 64k -ac 1 " + outputPath
    print(command)
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
    process.wait()
    if isTemp:
        os.remove(inputPath)

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
