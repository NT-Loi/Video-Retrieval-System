import requests

import config
from utils.video_metadata import load_video_metadata

url = "http://192.168.28.151:5000/api/v2/login"

data = {"username": "team004", "password": "123456"}

response = requests.post(url, json=data, verify=False)
url = "http://192.168.28.151:5000/api/v2/client/evaluation/list"

params = {"session": f"{response.json()['sessionId']}"}

response = requests.get(url, params=params)

url = f"http://192.168.28.151:5000/api/v2/submit/{response.json()[0]['id']}"

# Cập nhật đường dẫn file metadata
VIDEO_METADATA = load_video_metadata("video_metadata.json")

video = "L03_V030"
start = 15927
end = start
fps = VIDEO_METADATA.get(video, 25.0)

data = {
    "answerSets": [
        {
            "answers": [
                {
                    "mediaItemName": video,
                    "start": f"{int(float(start/fps) * 1000)}",
                    "end": f"{int(float(end/fps) * 1000)}",
                }
            ]
        }
    ]
}

response = requests.post(url, json=data, params=params)

print(response.status_code)
print(response.json())

