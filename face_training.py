import cv2
import numpy as np
from PIL import Image
import os

path = 'dataset'

recognizer = cv2.face.LBPHFaceRecognizer_create()
detector = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')

# Tự động tạo thư mục lưu model
if not os.path.exists('trainer'):
    os.makedirs('trainer')

# Lấy ảnh và tên người
def getImagesAndLabels(path):
    imagePaths = [os.path.join(path, f) for f in os.listdir(path)]
    faceSamples = []
    names = []
    name_to_id = {}
    next_id = 1

    for imagePath in imagePaths:
        PIL_img = Image.open(imagePath).convert('L')
        img_numpy = np.array(PIL_img, 'uint8')

        # Tách tên người từ tên file
        name = os.path.split(imagePath)[-1].split(".")[0]

        # Gán ID cho mỗi tên duy nhất
        if name not in name_to_id:
            name_to_id[name] = next_id
            next_id += 1

        id = name_to_id[name]
        faces = detector.detectMultiScale(img_numpy)

        for (x, y, w, h) in faces:
            faceSamples.append(img_numpy[y:y + h, x:x + w])
            names.append(id)

    return faceSamples, names, name_to_id


print("\n[INFO] Đang huấn luyện khuôn mặt, vui lòng chờ ...")
faces, ids, name_to_id = getImagesAndLabels(path)
recognizer.train(faces, np.array(ids))

recognizer.write('trainer/trainer.yml')
np.save('trainer/names.npy', name_to_id)

print(f"\n[INFO] Đã huấn luyện {len(name_to_id)} người: {list(name_to_id.keys())}")
print("\n[INFO] Hoàn tất huấn luyện và lưu mô hình.")
