import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext.jsx';

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const [deviceId, setDeviceId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (loading) {
    return <main className="center-page">Đang kiểm tra đăng nhập…</main>;
  }

  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      await login(deviceId.trim(), password);
      navigate('/dashboard', { replace: true });
    } catch (loginError) {
      setError(loginError.message || 'Không thể đăng nhập.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <div className="brand-mark" aria-hidden="true">SD</div>
        <h1 id="login-title">SmartDry Rack</h1>
        <p className="login-subtitle">Đăng nhập thiết bị</p>

        <form onSubmit={handleSubmit} noValidate>
          <label htmlFor="device-id">Device ID</label>
          <input
            id="device-id"
            name="deviceId"
            value={deviceId}
            onChange={(event) => setDeviceId(event.target.value)}
            autoComplete="username"
            autoFocus
            disabled={submitting}
          />

          <label htmlFor="password">Mật khẩu</label>
          <input
            id="password"
            name="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            disabled={submitting}
          />

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" disabled={submitting}>
            {submitting ? 'Đang đăng nhập…' : 'Đăng nhập'}
          </button>
        </form>
      </section>
    </main>
  );
}
