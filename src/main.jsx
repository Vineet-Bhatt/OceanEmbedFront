import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';

const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

function App() {
  const [status, setStatus] = useState('Choose a location and date to request a temperature profile.');
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState(null);

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    setBusy(true);
    setProfile(null);
    setStatus('Requesting profile…');
    try {
      const response = await fetch(`${API_URL}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          latitude: Number(data.get('latitude')),
          longitude: Number(data.get('longitude')),
          date: data.get('date'),
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `Prediction failed (${response.status}).`);
      setProfile(body);
      setStatus('Profile received.');
    } catch (error) {
      setStatus(error.message === 'Failed to fetch'
        ? `Could not reach the API at ${API_URL}. Start the FastAPI server and try again.`
        : error.message);
    } finally {
      setBusy(false);
    }
  }

  return <main className="page-shell">
    <a className="back-link" href="index.html">&larr; Back to OceanEmbed</a>
    <header className="hero">
      <p className="eyebrow">OCEANEMBED | PROFILE RECONSTRUCTION</p>
      <h1>Explore a subsurface temperature profile</h1>
      <p className="intro">Select a day and a point in the North Indian Ocean. The prototype is designed to reconstruct temperature through the water column from seven days of satellite and ocean surface observations.</p>
    </header>
    <section className="panel" aria-labelledby="request-title">
      <div className="panel-heading"><div><p className="eyebrow">MODEL INPUT</p><h2 id="request-title">Choose a location and date</h2></div><span className="grid-tag">0.25&deg; DAILY GRID</span></div>
      <form id="prediction-form" onSubmit={submit}>
        <label>Latitude (5&deg;N to 30&deg;N)<input name="latitude" type="number" min="5" max="30" step="0.25" defaultValue="15" required /></label>
        <label>Longitude (45&deg;E to 105&deg;E)<input name="longitude" type="number" min="45" max="105" step="0.25" defaultValue="75" required /></label>
        <label className="date-field">Target date<input name="date" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required /></label>
        <button type="submit" disabled={busy}>{busy ? 'REQUESTING PROFILE…' : 'PREDICT TEMPERATURE PROFILE'} <span aria-hidden="true">&rarr;</span></button>
      </form>
      <p className="status status-notice" role="status" aria-live="polite">{status}</p>
      {profile && <section className="result" aria-label="Predicted temperature profile">
        <h2>Temperature profile · {profile.date}</h2>
        <p>{profile.latitude}°N, {profile.longitude}°E</p>
        <div className="profile-table"><div className="profile-row profile-head"><span>Depth (m)</span><span>Temperature (°C)</span></div>
          {profile.profile.map(point => <div className="profile-row" key={point.depth_m}><span>{point.depth_m}</span><span>{point.temperature_c.toFixed(2)}</span></div>)}
        </div>
      </section>}
    </section>
    <section className="facts" aria-label="Prototype details">
      <article><span>INPUT WINDOW</span><strong>7 days</strong><p>SST, salinity, sea level anomaly, currents (u/v), and winds (u/v).</p></article>
      <article><span>PROFILE OUTPUT</span><strong>15 depths</strong><p>Temperature levels from the surface to 1,000 m.</p></article>
      <article><span>MEAN RMSE</span><strong>0.415 °C</strong><p>Jan 2024 prototype split, averaged across the 15 depth levels.</p></article>
      <article><span>MEAN R²</span><strong>0.923</strong><p>Reported for the same Jan 2024 prototype split.</p></article>
      <article className="architecture"><span>MODEL ARCHITECTURE</span><strong>Conv3D + FWinFormer-style block</strong><p>Temporal window attention and an FFT gate, with depth embeddings and monthly climatology. A thermocline-aware loss weights vertical temperature gradients. The model has 109,153 parameters.</p></article>
      <article><span>VALIDATION STATUS</span><strong>Prototype</strong><p>Extended chronological multi-year testing and Argo validation are planned.</p></article>
    </section>
    <footer>Multi-horizon forecasting is planned for a later phase; it is not available in this prototype.</footer>
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);
