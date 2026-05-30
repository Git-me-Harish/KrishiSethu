import React, { useState } from 'react';
import DiseaseDetection from './components/DiseaseDetection';
import CommunityQA from './components/CommunityQA';

function App() {
  const [activeTab, setActiveTab] = useState('detection');

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-green-700 text-white p-4 shadow-md">
        <div className="max-w-4xl mx-auto flex justify-between items-center">
          <h1 className="text-2xl font-bold">CropCare Pro</h1>
          <nav>
            <button
              className={`px-4 py-2 rounded-md mr-2 ${activeTab === 'detection' ? 'bg-green-800' : 'hover:bg-green-600'}`}
              onClick={() => setActiveTab('detection')}
            >
              Scanner
            </button>
            <button
              className={`px-4 py-2 rounded-md ${activeTab === 'community' ? 'bg-green-800' : 'hover:bg-green-600'}`}
              onClick={() => setActiveTab('community')}
            >
              Community
            </button>
          </nav>
        </div>
      </header>

      <main className="py-8">
        {activeTab === 'detection' ? <DiseaseDetection /> : <CommunityQA />}
      </main>

      <footer className="bg-gray-800 text-white text-center p-4 mt-auto">
        <p>© 2024 CropCare Pro - Empowering Farmers</p>
      </footer>
    </div>
  );
}

export default App;
