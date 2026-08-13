import { Navigate, Outlet } from 'react-router-dom';

import { useAuth } from './AuthContext.jsx';

export default function ProtectedRoute() {
  const { user, loading } = useAuth();

  if (loading) {
    return <main className="center-page">Đang kiểm tra đăng nhập…</main>;
  }

  return user ? <Outlet /> : <Navigate to="/login" replace />;
}
