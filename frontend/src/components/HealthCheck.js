import React, { useState, useEffect } from 'react';
import axios from 'axios';

function HealthCheck() {
  const [status, setStatus] = useState(null);
  const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';

  useEffect(() => {
    axios.get(`${apiUrl}/health`)
      .then(response => setStatus(response.data))
      .catch(error => setStatus({ error: error.message }));
  }, []);

  return (
    <section>
      <h2>Health Check</h2>
      {status ? (
        <pre>{JSON.stringify(status, null, 2)}</pre>
      ) : (
        <p>Loading...</p>
      )}
    </section>
  );
}

export default HealthCheck;
