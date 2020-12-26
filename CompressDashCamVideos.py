import argparse
import datetime
import os
import shutil
import subprocess
import tempfile

def getDatetime(dtStr, model):
    if model == "s80wifi": # YYYY_MMDD_HHMMSS_123A/B.mp4
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


def filenamesInDir(dir):
    filenames = [f for f in os.listdir(dir) if not f.startswith(".") and os.path.isfile(os.path.join(dir, f))]
    filenames.sort()
    return filenames

def compressVideos(outputDir, processor, model, clean):
    filenames = filenamesInDir(outputDir)
    if len(filenames) == 0:
        print("Output directory is empty: " + outputDir)
        return
    if model == "s80wifi":
        for i in range(len(filenames)):
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
                    command = "ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]scale=iw/3:ih/3,crop=iw:ih*3/4:0:ih/8[pip];[1][pip] overlay=main_w/3:0\" -c:v libx265 -x265-params log-level=error -crf 30 -c:a aac -b:a 64k -ac 1 " + outputPath
                elif processor == 1: # Nvidia GPU
                    command = "ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]scale=iw/3:ih/3,crop=iw:ih*3/4:0:ih/8[pip];[1][pip] overlay=main_w/3:0\" -c:v hevc_nvenc -rc constqp -qp 37 -c:a aac -b:a 64k -ac 1 " + outputPath 
                elif processor == 2: # AMD GPU
                    command = "ffmpeg -stats -loglevel error -i " + overlayFile + " -i " + mainFile + " -filter_complex \"[0]scale=iw/3:ih/3,crop=iw:ih*3/4:0:ih/8[pip];[1][pip] overlay=main_w/3:0\" -c:v hevc_videotoolbox -c:a aac -b:a 64k -ac 1 " + outputPath 
                else:
                    print("Unknown processor parameter")
                print("Compressing PIP video \t" + outputPath)
                process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
                process.wait()
                if clean and os.path.exists(outputPath) and os.path.getsize(outputPath) > 0:
                    print("Deleting temp file \t" + mainFile)
                    os.remove(mainFile)
                    print("Deleting temp file \t" + overlayFile)
                    os.remove(overlayFile)
            # If only A or B is found, and file still exists, compress it only
            elif filenameCurr.endswith("A.MP4") or filenameCurr.endswith("B.MP4"):
                mainFile = os.path.join(outputDir, filenameCurr)
                if os.path.exists(mainFile):
                    outputPath = mainFile[:-5] + ".mp4"
                    if processor == 0: # CPU
                        command = "ffmpeg -stats -loglevel error -i " + mainFile + " -c:v libx265 -x265-params log-level=error -crf 30 -c:a aac -b:a 64k -ac 1 " + outputPath
                    elif processor == 1: # Nvidia GPU
                        command = "ffmpeg -stats -loglevel error -i " + mainFile + " -c:v hevc_nvenc -rc constqp -qp 37 -c:a aac -b:a 64k -ac 1 " + outputPath 
                    elif processor == 2: # AMD GPU
                        command = "ffmpeg -stats -loglevel error -i " + mainFile + " -c:v hevc_videotoolbox -c:a aac -b:a 64k -ac 1 " + outputPath 
                    else:
                        print("Unknown processor parameter")
                    print("Compressing video \t" + outputPath)
                    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
                    process.wait()
                    if clean and os.path.exists(outputPath) > 0:
                        print("Deleting temp file \t" + mainFile)
                        os.remove(mainFile)
                # else: # Deleted together with the paired A/B file
                #     print("File not exits: " + mainFile)
    elif model == "s36":
        for i in range(len(filenames)):
            filePath = os.path.join(outputDir, filenames[i])
            if filePath.endswith(".MOV") and os.path.exists(filePath):
                outputPath = filePath[:-4] + ".mp4"
                if processor == 0: # CPU
                    command = "ffmpeg -stats -loglevel error -i " + filePath + " -c:v libx265 -x265-params log-level=error -crf 30 -c:a aac -b:a 64k -ac 1 " + outputPath
                elif processor == 1: # Nvidia GPU
                    command = "ffmpeg -stats -loglevel error -i " + filePath + " -c:v hevc_nvenc -rc constqp -qp 37 -c:a aac -b:a 64k -ac 1 " + outputPath 
                elif processor == 2: # AMD GPU
                    command = "ffmpeg -stats -loglevel error -i " + filePath + " -c:v hevc_videotoolbox -c:a aac -b:a 64k -ac 1 " + outputPath 
                else:
                    print("Unknown processor parameter")
                print("Compressing video \t" + outputPath)
                process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
                process.wait()
                if clean and os.path.exists(outputPath) > 0:
                    print("Deleting temp file \t" + mainFile)
                    os.remove(mainFile)



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
    if model == "s80wifi":
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

def process(inputDir, outputDir, clipLength, processor, model, clean):
    filenames = filenamesInDir(inputDir)
    if model == "s80wifi":
        filenamesA, filenamesB = [], []
        for filename in filenames:
            if filename.endswith("A.MP4"):
                filenamesA.append(filename)
            else:
                filenamesB.append(filename)
        catFiles(filenamesA, inputDir, outputDir, clipLength, model)
        catFiles(filenamesB, inputDir, outputDir, clipLength, model)
    elif model == "s36":
        catFiles(filenames, inputDir, outputDir, clipLength, model)
    compressVideos(outputDir, processor, model, clean)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", dest = "input", help = "Input Directory", type = str)
    parser.add_argument("-o", "--output", dest = "output", help = "Output Directory", type = str)
    parser.add_argument("-l", "--length", dest = "length", help = "Clip Length in second", type = int, default = 300)
    parser.add_argument("-p", "--processor", dest = "processor", help = "Process Type, 0 = CPU, 1 = Nvidia GPU, 2 = AMD GPU", type = int, default = 0)
    parser.add_argument("-m", "--model", dest = "model", help = "Dash cam model (s80wifi, s36)", type = str, default="s80wifi")
    parser.add_argument("-c", "--clean", dest = "clean", help = "Clean temp files", action='store_true')
    args = parser.parse_args()
    process(args.input, args.output, args.length, args.processor, args.model, args.clean)
