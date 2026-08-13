import { NavLink } from 'react-router-dom';

const navigationItems = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/monitor', label: 'Điều khiển' },
  { to: '/history', label: 'Lịch sử hoạt động' },
];

export default function TopNavigation({ deviceId, loggingOut, onLogout }) {
  return (
    <header className="top-bar">
      <div className="user-label" title={deviceId}>
        <span>USER:</span>
        <strong>{deviceId}</strong>
      </div>

      <nav className="primary-navigation" aria-label="Điều hướng chính">
        {navigationItems.map((item) => (
          <NavLink
            className={({ isActive }) => (
              `navigation-link${isActive ? ' active' : ''}`
            )}
            end
            key={item.to}
            to={item.to}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <button
        className="logout-button"
        type="button"
        onClick={onLogout}
        disabled={loggingOut}
      >
        {loggingOut ? 'Đang đăng xuất…' : 'Đăng xuất'}
      </button>
    </header>
  );
}
