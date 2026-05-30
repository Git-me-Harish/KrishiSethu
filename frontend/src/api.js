import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
});

export const predictDisease = async (imageFile) => {
  const formData = new FormData();
  formData.append('file', imageFile);

  const response = await api.post('/predict', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const getQuestions = async () => {
  const response = await api.get('/questions/');
  return response.data;
};

export const createQuestion = async (title, content, authorId) => {
  const response = await api.post('/questions/', {
    title,
    content,
    author_id: authorId
  });
  return response.data;
};

export const getAnswers = async (questionId) => {
  const response = await api.get(`/questions/${questionId}/answers/`);
  return response.data;
};

export const createAnswer = async (content, questionId, authorId) => {
  const response = await api.post('/answers/', {
    content,
    question_id: questionId,
    author_id: authorId
  });
  return response.data;
};
