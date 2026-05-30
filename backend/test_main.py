from fastapi.testclient import TestClient
from backend.main import app
from backend import models
from backend.database import Base, engine, SessionLocal
import io
from PIL import Image

# Recreate the database for testing
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

client = TestClient(app)

def test_create_user():
    db = SessionLocal()
    # Create a test user since user ID 1 is hardcoded in the frontend
    user = db.query(models.User).filter_by(username="test_farmer").first()
    if not user:
        user = models.User(username="test_farmer")
        db.add(user)
        db.commit()
    db.close()

def test_create_question():
    test_create_user() # Ensure user exists
    response = client.post(
        "/questions/",
        json={"title": "Test Question", "content": "This is a test.", "author_id": 1}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Test Question"

def test_read_questions():
    response = client.get("/questions/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_predict_disease_invalid_file():
    # Try to upload a text file instead of an image
    file_content = b"Not an image"
    response = client.post(
        "/predict",
        files={"file": ("test.txt", file_content, "text/plain")}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "File provided is not an image."

def test_predict_disease_valid_image():
    # Create a dummy image
    img = Image.new('RGB', (60, 30), color = 'red')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)

    response = client.post(
        "/predict",
        files={"file": ("test.jpg", img_byte_arr, "image/jpeg")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "prediction" in data
    assert "confidence" in data
