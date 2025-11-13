import cv2
import numpy as np
import serial
import time
import os

# ===== CẤU HÌNH =====
ARDUINO_PORT = 'COM6'
ARDUINO_BAUD = 9600
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

# Ngưỡng khoảng cách an toàn (cm)
SAFE_MIN = 40
SAFE_MAX = 60

# Vùng chết giữa màn hình để tránh dao động
CENTER_DEAD_ZONE = 80

# Ngưỡng confidence để nhận diện
CONFIDENCE_THRESHOLD = 60

# Kích thước khuôn mặt thực tế (cm)
FACE_REAL_WIDTH = 19
CALIBRATION_DISTANCE = 45

# Delay giữa các lệnh gửi (giây)
COMMAND_DELAY = 0.1

class FaceFollowRobot:
    def __init__(self):
        self.arduino = None
        self.recognizer = None
        self.cascade = None
        self.cam = None
        self.id_to_name = {}
        self.pixel_ratio = 0
        self.last_command = None
        self.last_command_time = 0
        
    def init_arduino(self):
        """Khởi tạo kết nối Arduino"""
        try:
            self.arduino = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=1)
            time.sleep(2)
            print(f"[✓] Đã kết nối Arduino trên {ARDUINO_PORT}")
            return True
        except Exception as e:
            print(f"[✗] Lỗi kết nối Arduino: {e}")
            return False
    
    def init_face_recognition(self):
        """Khởi tạo bộ nhận diện khuôn mặt"""
        try:
            # Kiểm tra file model
            if not os.path.exists('trainer/trainer.yml'):
                print("[✗] Không tìm thấy file trainer.yml. Chạy face_training.py trước!")
                return False
            
            if not os.path.exists('trainer/names.npy'):
                print("[✗] Không tìm thấy file names.npy. Chạy face_training.py trước!")
                return False
            
            # Load model
            self.recognizer = cv2.face.LBPHFaceRecognizer_create()
            self.recognizer.read('trainer/trainer.yml')
            
            # Load cascade
            self.cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
            
            # Load names
            name_to_id = np.load('trainer/names.npy', allow_pickle=True).item()
            self.id_to_name = {v: k for k, v in name_to_id.items()}
            
            print(f"[✓] Đã load model nhận diện: {list(name_to_id.keys())}")
            return True
        except Exception as e:
            print(f"[✗] Lỗi khởi tạo nhận diện: {e}")
            return False
    
    def init_camera(self):
        """Khởi tạo camera"""
        try:
            self.cam = cv2.VideoCapture(0)
            self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            
            # Kiểm tra camera
            ret, _ = self.cam.read()
            if not ret:
                print("[✗] Không thể mở camera")
                return False
            
            print("[✓] Camera đã sẵn sàng")
            return True
        except Exception as e:
            print(f"[✗] Lỗi khởi tạo camera: {e}")
            return False
    
    def calibrate_distance(self):
        """Hiệu chuẩn khoảng cách từ ảnh mẫu"""
        try:
            if not os.path.exists('Test.jpg'):
                print("[!] Không tìm thấy Test.jpg, dùng giá trị mặc định")
                self.pixel_ratio = 500  # Giá trị mặc định
                return True
            
            sample_img = cv2.imread('Test.jpg')
            gray = cv2.cvtColor(sample_img, cv2.COLOR_BGR2GRAY)
            faces = self.cascade.detectMultiScale(gray, 1.3, 5)
            
            if len(faces) > 0:
                w_sample = faces[0][2]
                self.pixel_ratio = (w_sample * CALIBRATION_DISTANCE) / FACE_REAL_WIDTH
                print(f"[✓] Đã hiệu chuẩn khoảng cách (pixel_ratio: {self.pixel_ratio:.2f})")
            else:
                print("[!] Không phát hiện khuôn mặt trong Test.jpg")
                self.pixel_ratio = 500
            
            return True
        except Exception as e:
            print(f"[!] Lỗi hiệu chuẩn: {e}, dùng giá trị mặc định")
            self.pixel_ratio = 500
            return True
    
    def send_command(self, cmd, force=False):
        """Gửi lệnh đến Arduino với debouncing"""
        current_time = time.time()
        
        # Chỉ gửi nếu lệnh khác hoặc đã qua delay time hoặc force
        if force or cmd != self.last_command or \
           (current_time - self.last_command_time) > COMMAND_DELAY:
            try:
                self.arduino.write(cmd.encode())
                self.last_command = cmd
                self.last_command_time = current_time
            except Exception as e:
                print(f"[✗] Lỗi gửi lệnh: {e}")
    
    def calculate_distance(self, face_width):
        """Tính khoảng cách từ độ rộng khuôn mặt"""
        if face_width == 0 or self.pixel_ratio == 0:
            return 0
        distance = (FACE_REAL_WIDTH * CALIBRATION_DISTANCE) / face_width
        return round(distance, 1)
    
    def detect_and_recognize(self, frame):
        """Phát hiện và nhận diện khuôn mặt"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.cascade.detectMultiScale(gray, 1.3, 5)
        
        if len(faces) == 0:
            return None, None, None
        
        # Lấy khuôn mặt lớn nhất (gần nhất)
        face = max(faces, key=lambda f: f[2] * f[3])
        x, y, w, h = face
        
        # Nhận diện
        roi_gray = gray[y:y+h, x:x+w]
        id, confidence = self.recognizer.predict(roi_gray)
        
        if confidence < CONFIDENCE_THRESHOLD:
            name = self.id_to_name.get(id, "Unknown")
        else:
            name = "Unknown"
        
        return face, name, confidence
    
    def control_robot(self, face_box, name):
        """Điều khiển robot theo vị trí khuôn mặt"""
        if name == "Unknown":
            self.send_command('S')
            return
        
        x, y, w, h = face_box
        
        # Tính khoảng cách
        distance = self.calculate_distance(w)
        
        # Tìm tâm khuôn mặt và màn hình
        center_face = x + w/2
        center_screen = CAMERA_WIDTH / 2
        
        # Ưu tiên xoay trước
        if center_face < center_screen - CENTER_DEAD_ZONE:
            self.send_command('L')  # Xoay trái
            return
        elif center_face > center_screen + CENTER_DEAD_ZONE:
            self.send_command('R')  # Xoay phải
            return
        
        # Nếu đã thẳng, điều chỉnh khoảng cách
        if distance > SAFE_MAX:
            self.send_command('F')  # Tiến
        elif distance < SAFE_MIN:
            self.send_command('B')  # Lùi
        else:
            self.send_command('S')  # Dừng
        
        return distance
    
    def draw_info(self, frame, face_box, name, confidence, distance=None):
        """Vẽ thông tin lên frame"""
        if face_box is None:
            return
        
        x, y, w, h = face_box
        
        # Vẽ hình chữ nhật
        color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
        
        # Hiển thị tên
        cv2.putText(frame, name, (x, y-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        # Hiển thị confidence
        conf_text = f"Conf: {100-confidence:.1f}%"
        cv2.putText(frame, conf_text, (x, y+h+20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        
        # Hiển thị khoảng cách
        if distance is not None:
            dist_text = f"Distance: {distance} cm"
            cv2.putText(frame, dist_text, (x, y+h+45), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        # Vẽ tâm màn hình
        cv2.line(frame, (CAMERA_WIDTH//2, 0), (CAMERA_WIDTH//2, CAMERA_HEIGHT), 
                 (255, 0, 0), 1)
    
    def run(self):
        """Chạy chương trình chính"""
        print("\n" + "="*50)
        print("  ROBOT THEO DÕI CHỦ NHÂN")
        print("="*50 + "\n")
        
        # Khởi tạo các thành phần
        if not self.init_arduino():
            return
        if not self.init_face_recognition():
            return
        if not self.init_camera():
            return
        if not self.calibrate_distance():
            return
        
        print("\n[✓] Hệ thống đã sẵn sàng!")
        print("[i] Nhấn ESC để thoát\n")
        
        try:
            while True:
                ret, frame = self.cam.read()
                if not ret:
                    print("[✗] Không thể đọc frame từ camera")
                    break
                
                frame = cv2.flip(frame, 1)
                
                # Phát hiện và nhận diện
                face_box, name, confidence = self.detect_and_recognize(frame)
                
                if face_box is not None:
                    # Điều khiển robot
                    distance = self.control_robot(face_box, name)
                    
                    # Vẽ thông tin
                    self.draw_info(frame, face_box, name, confidence, distance)
                else:
                    # Không phát hiện khuôn mặt
                    self.send_command('S')
                    cv2.putText(frame, "No face detected", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                
                # Hiển thị FPS
                cv2.putText(frame, f"CMD: {self.last_command or 'None'}", (10, CAMERA_HEIGHT-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                cv2.imshow("Follow Owner Robot", frame)
                
                # Thoát khi nhấn ESC
                if cv2.waitKey(1) & 0xFF == 27:
                    break
        
        except KeyboardInterrupt:
            print("\n[!] Đã dừng bởi người dùng")
        
        finally:
            # Dừng robot
            self.send_command('S', force=True)
            
            # Giải phóng tài nguyên
            if self.cam:
                self.cam.release()
            cv2.destroyAllWindows()
            if self.arduino:
                self.arduino.close()
            
            print("\n[✓] Đã tắt hệ thống an toàn")

# ===== CHẠY CHƯƠNG TRÌNH =====
if __name__ == "__main__":
    robot = FaceFollowRobot()
    robot.run()