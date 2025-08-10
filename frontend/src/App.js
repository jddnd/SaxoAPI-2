import React from 'react';
import HealthCheck from './components/HealthCheck';
import SignalForm from './components/SignalForm';
import './App.css';

function App() {
  return (
    <div className="App">
      <h1>Saxo Auto Trader</h1>
      <HealthCheck />
      <SignalForm />
    </div>
  );
}

export default App;