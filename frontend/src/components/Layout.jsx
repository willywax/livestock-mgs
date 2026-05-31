import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  House,
  MapPin,
  Tag,
  CalendarBlank,
  Scales,
  ChartBar,
  Users,
  SignOut,
  List,
  X,
  Cow,
  Gear,
  FirstAidKit,
} from '@phosphor-icons/react';
import { Button } from './ui/button';
import { cn } from '../lib/utils';

const navItems = [
  { path: '/', icon: House, label: 'Dashboard', roles: ['admin', 'data_entry', 'viewer'] },
  { path: '/locations', icon: MapPin, label: 'Locations', roles: ['admin', 'data_entry', 'viewer'] },
  { path: '/animals', icon: Tag, label: 'Animals', roles: ['admin', 'data_entry', 'viewer'] },
  { path: '/farm-health', icon: FirstAidKit, label: 'Farm Health', roles: ['admin', 'data_entry', 'viewer'] },
  { path: '/daily-logs', icon: CalendarBlank, label: 'Daily Logs', roles: ['admin', 'data_entry', 'viewer'] },
  { path: '/opening-balances', icon: Scales, label: 'Opening Balances', roles: ['admin'] },
  { path: '/reports', icon: ChartBar, label: 'Reports', roles: ['admin', 'data_entry', 'viewer'] },
  { path: '/settings', icon: Gear, label: 'Settings', roles: ['admin'] },
  { path: '/admin/users', icon: Users, label: 'Users', roles: ['admin'] },
];

export const Layout = ({ children }) => {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const filteredNav = navItems.filter(item => item.roles.includes(user?.role));

  return (
    <div className="min-h-screen bg-background">
      {/* Mobile Header */}
      <header className="lg:hidden fixed top-0 left-0 right-0 h-16 bg-card border-b border-border z-50 flex items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <Cow weight="fill" className="h-8 w-8 text-primary" />
          <span className="font-heading font-bold text-xl text-primary">ShambaManager</span>
        </div>
        <Button 
          variant="ghost" 
          size="icon"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          data-testid="mobile-menu-btn"
        >
          {sidebarOpen ? <X className="h-6 w-6" /> : <List className="h-6 w-6" />}
        </Button>
      </header>

      {/* Sidebar */}
      <aside className={cn(
        "fixed top-0 left-0 h-full w-64 bg-card border-r border-border z-40 transition-transform duration-300",
        "lg:translate-x-0",
        sidebarOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <div className="p-6 border-b border-border hidden lg:flex items-center gap-3">
          <Cow weight="fill" className="h-10 w-10 text-primary" />
          <div>
            <h1 className="font-heading font-bold text-xl text-primary">ShambaManager</h1>
            <p className="text-xs text-muted-foreground">Livestock Management</p>
          </div>
        </div>
        
        <nav className="p-4 mt-16 lg:mt-0 space-y-1">
          {filteredNav.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path || 
              (item.path !== '/' && location.pathname.startsWith(item.path));
            
            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setSidebarOpen(false)}
                data-testid={`nav-${item.label.toLowerCase().replace(' ', '-')}`}
                className={cn(
                  "flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200",
                  isActive 
                    ? "bg-primary text-primary-foreground" 
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                <Icon className="h-5 w-5" weight={isActive ? "fill" : "regular"} />
                <span className="font-medium">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-border">
          <div className="flex items-center gap-3 mb-3 px-2">
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
              <span className="text-primary font-semibold">
                {user?.name?.charAt(0)?.toUpperCase()}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-sm truncate">{user?.name}</p>
              <p className="text-xs text-muted-foreground capitalize">{user?.role?.replace('_', ' ')}</p>
            </div>
          </div>
          <Button 
            variant="outline" 
            className="w-full justify-start gap-2"
            onClick={handleLogout}
            data-testid="logout-btn"
          >
            <SignOut className="h-4 w-4" />
            Logout
          </Button>
        </div>
      </aside>

      {/* Overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main Content */}
      <main className="lg:ml-64 pt-16 lg:pt-0 min-h-screen">
        <div className="p-4 md:p-6 lg:p-8">
          {children}
        </div>
      </main>
    </div>
  );
};
