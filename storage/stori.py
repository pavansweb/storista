import requests
import tkinter as tk
from tkinter import filedialog
import os


UPLOAD_URL = "https://storista.vercel.app/upload"

def choose_file_and_upload():
    root = tk.Tk()
    root.withdraw()  

    file_path = filedialog.askopenfilename(title=" ")
    if not file_path:
        print(" ")
        return

    filename = os.path.basename(file_path)
    print(f"...")

    with open(file_path, 'rb') as f:
        files = {'file': (filename, f)}
        try:
            resp = requests.post(UPLOAD_URL, files=files)
        except Exception as e:
            print("Error during upload:", e)
            return

    if resp.ok:
        print("Ok ")
        print(resp.text)
        input()
    else:
        print(f"{resp.status_code}")
        print("Response content:", resp.text)
        input()


if __name__ == "__main__":
    choose_file_and_upload()
