import numpy as np
import tensorflow as tf
from PIL import Image
import io
import os

# Get path relative to the current file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "CROP---Plant-Disease-Identification-Using-App-master", "Cnn-Code", "OutputFiles", "output.tflite")

CLASSES = [
    "Potato___Early_blight",
    "Potato___Late_blight",
    "Potato___healthy",
    "Tomato___Bacterial_spot",
    "Tomato___Early_blight",
    "Tomato___Late_blight",
    "Tomato___Leaf_Mold",
    "Tomato___Septoria_leaf_spot",
    "Tomato___Spider_mites Two-spotted_spider_mite",
    "Tomato___Target_Spot",
    "Tomato___Tomato_mosaic_virus",
    "Tomato___healthy"
]

class MLService:
    def __init__(self):
        try:
            self.interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
            self.interpreter.allocate_tensors()
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            print("Successfully loaded TFLite model.")
        except Exception as e:
            print(f"Error loading TFLite model: {e}")
            self.interpreter = None

    def preprocess_image(self, image_bytes):
        # Open image from bytes
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if it has an alpha channel or is grayscale
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Resize to 256x256 as required by the model
        img = img.resize((256, 256))

        # Convert to numpy array and rescale to 1./255
        img_array = np.array(img, dtype=np.float32)
        img_array = img_array / 255.0

        # Expand dimensions to match batch size: (1, 256, 256, 3)
        img_array = np.expand_dims(img_array, axis=0)
        return img_array

    def predict(self, image_bytes):
        if not self.interpreter:
            return {"prediction": "Model not loaded", "confidence": "0"}

        try:
            input_data = self.preprocess_image(image_bytes)

            self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
            self.interpreter.invoke()

            output_data = self.interpreter.get_tensor(self.output_details[0]['index'])

            # The output is likely softmax probabilities
            predicted_class_index = np.argmax(output_data[0])
            confidence = float(np.max(output_data[0]))

            predicted_class = CLASSES[predicted_class_index]

            return {
                "prediction": predicted_class,
                "confidence": f"{confidence:.2f}"
            }
        except Exception as e:
            return {"prediction": f"Error: {str(e)}", "confidence": "0"}

ml_service = MLService()
