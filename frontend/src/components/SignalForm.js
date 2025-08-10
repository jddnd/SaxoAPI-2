import React, { useState } from 'react';
import axios from 'axios';

function SignalForm() {
  const [formData, setFormData] = useState({
    symbol: '',
    price: ''
  });
  const [response, setResponse] = useState(null);
  const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const res = await axios.post(`${apiUrl}/signal`, {
        symbol: formData.symbol,
        price: parseFloat(formData.price) || undefined
      });
      setResponse(res.data);
    } catch (error) {
      setResponse({ error: error.response?.data?.detail || error.message });
    }
  };

  return (
    <section>
      <h2>Send Signal</h2>
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          name="symbol"
          placeholder="Symbol (e.g., AAPL)"
          value={formData.symbol}
          onChange={handleChange}
          required
        />
        <input
          type="number"
          name="price"
          placeholder="Price"
          value={formData.price}
          onChange={handleChange}
        />
        <button type="submit">Send Signal</button>
      </form>
      {response && <pre>{JSON.stringify(response, null, 2)}</pre>}
    </section>
  );
}

export default SignalForm;
