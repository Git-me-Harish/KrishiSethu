import React, { useState, useEffect } from 'react';
import { getQuestions, createQuestion, getAnswers, createAnswer } from '../api';

const CommunityQA = () => {
  const [questions, setQuestions] = useState([]);
  const [newQuestionTitle, setNewQuestionTitle] = useState('');
  const [newQuestionContent, setNewQuestionContent] = useState('');
  const [activeQuestionId, setActiveQuestionId] = useState(null);
  const [answers, setAnswers] = useState({});
  const [newAnswerContent, setNewAnswerContent] = useState('');
  const [loading, setLoading] = useState(false);

  // Hardcoded user ID for demonstration purposes
  const CURRENT_USER_ID = 1;

  useEffect(() => {
    fetchQuestions();
  }, []);

  const fetchQuestions = async () => {
    setLoading(true);
    try {
      const data = await getQuestions();
      setQuestions(data);
    } catch (error) {
      console.error("Error fetching questions:", error);
    } finally {
      setLoading(false);
    }
  };

  const fetchAnswers = async (questionId) => {
    try {
      const data = await getAnswers(questionId);
      setAnswers(prev => ({ ...prev, [questionId]: data }));
    } catch (error) {
      console.error("Error fetching answers:", error);
    }
  };

  const handleAskQuestion = async (e) => {
    e.preventDefault();
    if (!newQuestionTitle.trim() || !newQuestionContent.trim()) return;

    try {
      await createQuestion(newQuestionTitle, newQuestionContent, CURRENT_USER_ID);
      setNewQuestionTitle('');
      setNewQuestionContent('');
      fetchQuestions();
    } catch (error) {
      console.error("Error creating question:", error);
    }
  };

  const handlePostAnswer = async (e, questionId) => {
    e.preventDefault();
    if (!newAnswerContent.trim()) return;

    try {
      await createAnswer(newAnswerContent, questionId, CURRENT_USER_ID);
      setNewAnswerContent('');
      fetchAnswers(questionId);
    } catch (error) {
      console.error("Error creating answer:", error);
    }
  };

  const toggleQuestion = (questionId) => {
    if (activeQuestionId === questionId) {
      setActiveQuestionId(null);
    } else {
      setActiveQuestionId(questionId);
      if (!answers[questionId]) {
        fetchAnswers(questionId);
      }
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-4">
      <h2 className="text-3xl font-bold text-green-800 mb-6 border-b-2 border-green-200 pb-2">Community Q&A</h2>

      {/* Ask Question Form */}
      <div className="bg-white p-6 rounded-lg shadow-md mb-8 border-l-4 border-green-500">
        <h3 className="text-xl font-semibold mb-4 text-gray-800">Ask the Community</h3>
        <form onSubmit={handleAskQuestion}>
          <div className="mb-4">
            <label className="block text-gray-700 text-sm font-bold mb-2" htmlFor="title">
              Question Title
            </label>
            <input
              id="title"
              type="text"
              value={newQuestionTitle}
              onChange={(e) => setNewQuestionTitle(e.target.value)}
              className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:ring-2 focus:ring-green-500"
              placeholder="E.g., Yellow spots on tomato leaves?"
              required
            />
          </div>
          <div className="mb-4">
            <label className="block text-gray-700 text-sm font-bold mb-2" htmlFor="content">
              Details
            </label>
            <textarea
              id="content"
              value={newQuestionContent}
              onChange={(e) => setNewQuestionContent(e.target.value)}
              className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:ring-2 focus:ring-green-500 h-24"
              placeholder="Provide more details about the issue..."
              required
            />
          </div>
          <button
            type="submit"
            className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-6 rounded focus:outline-none focus:shadow-outline transition duration-150"
          >
            Post Question
          </button>
        </form>
      </div>

      {/* Questions List */}
      <div>
        <h3 className="text-2xl font-semibold mb-4 text-gray-800">Recent Questions</h3>
        {loading && questions.length === 0 ? (
          <p className="text-gray-600">Loading questions...</p>
        ) : questions.length === 0 ? (
          <p className="text-gray-600 italic bg-gray-50 p-4 rounded">No questions yet. Be the first to ask!</p>
        ) : (
          <div className="space-y-4">
            {questions.map((q) => (
              <div key={q.id} className="bg-white rounded-lg shadow overflow-hidden">
                <div
                  className="p-4 cursor-pointer hover:bg-gray-50 transition duration-150"
                  onClick={() => toggleQuestion(q.id)}
                >
                  <h4 className="text-lg font-bold text-green-700">{q.title}</h4>
                  <p className="text-gray-600 mt-2">{q.content}</p>
                </div>

                {/* Answers Section (Expandable) */}
                {activeQuestionId === q.id && (
                  <div className="bg-gray-50 p-4 border-t border-gray-200">
                    <h5 className="font-bold text-gray-700 mb-3">Answers</h5>

                    {answers[q.id] && answers[q.id].length > 0 ? (
                      <ul className="space-y-3 mb-4">
                        {answers[q.id].map(a => (
                          <li key={a.id} className="bg-white p-3 rounded border border-gray-200 shadow-sm text-gray-700">
                            {a.content}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-gray-500 italic mb-4 text-sm">No answers yet. Can you help?</p>
                    )}

                    {/* Add Answer Form */}
                    <form onSubmit={(e) => handlePostAnswer(e, q.id)} className="mt-2 flex">
                      <input
                        type="text"
                        value={newAnswerContent}
                        onChange={(e) => setNewAnswerContent(e.target.value)}
                        className="shadow appearance-none border rounded-l w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:ring-1 focus:ring-green-500"
                        placeholder="Write an answer..."
                        required
                      />
                      <button
                        type="submit"
                        className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded-r focus:outline-none"
                      >
                        Reply
                      </button>
                    </form>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default CommunityQA;
