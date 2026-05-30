import React, { useState } from 'react';
import { predictDisease } from '../api';

const DiseaseDetection = () => {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      setFile(selectedFile);
      setPreview(URL.createObjectURL(selectedFile));
      setPrediction(null);
      setError(null);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setError("Please select an image first.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await predictDisease(file);
      setPrediction(data);
    } catch (err) {
      setError("Failed to analyze the image. Please try again.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const getRemedies = (disease) => {
    if (disease.includes('healthy')) return "Your plant is healthy! Keep up the good work.";
    if (disease.includes('Early_blight')) return "Remove affected leaves. Apply copper-based fungicide.";
    if (disease.includes('Late_blight')) return "Ensure good airflow. Apply appropriate fungicide immediately.";
    if (disease.includes('Bacterial_spot')) return "Avoid overhead watering. Remove infected plant debris.";
    return "Please consult a local agricultural expert for specific remedies.";
  };

  return (
    <div className="max-w-md mx-auto bg-white rounded-xl shadow-md overflow-hidden md:max-w-2xl p-6 m-4">
      <h2 className="text-2xl font-bold mb-4 text-green-800">Crop Disease Detection</h2>
      <p className="mb-6 text-gray-600">Upload a photo of your tomato or potato plant leaf to detect diseases instantly.</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex items-center justify-center w-full">
            <label className="flex flex-col w-full h-32 border-4 border-dashed hover:bg-gray-100 hover:border-green-300 group cursor-pointer">
                <div className="flex flex-col items-center justify-center pt-7">
                  <svg className="w-10 h-10 text-gray-400 group-hover:text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                  <p className="pt-1 text-sm tracking-wider text-gray-400 group-hover:text-green-600">
                    {file ? file.name : "Select a photo"}
                  </p>
                </div>
                <input type="file" className="opacity-0" accept="image/*" onChange={handleFileChange} />
            </label>
        </div>

        {preview && (
          <div className="mt-4 flex justify-center">
            <img src={preview} alt="Preview" className="h-48 object-cover rounded-lg" />
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-green-600 text-white font-bold py-2 px-4 rounded hover:bg-green-700 focus:outline-none focus:shadow-outline disabled:opacity-50"
        >
          {loading ? 'Analyzing...' : 'Analyze Image'}
        </button>
      </form>

      {error && (
        <div className="mt-4 p-3 bg-red-100 text-red-700 rounded border border-red-400">
          {error}
        </div>
      )}

      {prediction && (
        <div className="mt-6 p-4 bg-green-50 rounded-lg border border-green-200">
          <h3 className="text-xl font-semibold text-green-900 mb-2">Analysis Result</h3>
          <div className="mb-2">
            <span className="font-bold text-gray-700">Detected: </span>
            <span className="text-lg text-green-800">{prediction.prediction.replace(/___/g, ' - ').replace(/_/g, ' ')}</span>
          </div>
          <div className="mb-4">
            <span className="font-bold text-gray-700">Confidence: </span>
            <span className="text-gray-800">{(parseFloat(prediction.confidence) * 100).toFixed(1)}%</span>
          </div>
          <div>
            <h4 className="font-bold text-gray-700 mb-1">Recommended Action:</h4>
            <p className="text-gray-700 bg-white p-3 rounded shadow-sm">
              {getRemedies(prediction.prediction)}
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default DiseaseDetection;
