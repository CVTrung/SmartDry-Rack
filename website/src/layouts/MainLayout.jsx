import { useState } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext.jsx';
import TopNavigation from '../components/TopNavigation.jsx';

export default function MainLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState('');

  async function handleLogout() {
    setLogoutError('');
    setLoggingOut(true);

    try {
      await logout();
      navigate('/login', { replace: true });
    } catch (error) {
      setLogoutError(error.message || 'Không thể đăng xuất.');
      setLoggingOut(false);
    }
  }

  return (
    <div className="app-shell">
      <TopNavigation
        deviceId={user.device_id}
        loggingOut={loggingOut}
        onLogout={handleLogout}
      />

      {logoutError && (
        <p className="layout-error" role="alert">
          {logoutError}
        </p>
      )}

      <main className="page-content" id="main-content">
        <Outlet />
      </main>
    </div>
  );
}
